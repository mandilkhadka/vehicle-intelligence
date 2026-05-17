/**
 * Backend API server entry point
 * Production-ready Express server with security, logging, and error handling
 */

import express, { Express, Request } from "express";
import cors from "cors";
import helmet from "helmet";
import compression from "compression";
import rateLimit from "express-rate-limit";
import pinoHttp from "pino-http";
import path from "path";
import { config } from "./config/env";
import logger from "./utils/logger";
import * as fs from "fs";
import { initDatabase, getDatabase } from "./db/init";
import { reapStuckJobs, listVideosEligibleForCleanup } from "./models/inspection";
import { requestIdMiddleware } from "./middleware/requestId";
import { errorHandler, notFoundHandler } from "./middleware/errorHandler";
import uploadRouter from "./routes/upload";
import jobsRouter from "./routes/jobs";
import inspectionsRouter from "./routes/inspections";
import metricsRouter from "./routes/metrics";

// Initialize database
try {
  initDatabase();
  logger.info("Database initialized successfully");
} catch (error) {
  logger.fatal({ error }, "Failed to initialize database");
  process.exit(1);
}

// Reap orphaned jobs left behind by a previous crash so the frontend isn't
// stuck polling rows that nobody is processing.
try {
  const reaped = reapStuckJobs();
  if (reaped > 0) {
    logger.warn({ reaped }, "Marked stuck jobs as failed on startup");
  }
} catch (error) {
  logger.warn({ error }, "Failed to reap stuck jobs on startup (non-fatal)");
}

// Periodic reaper so jobs that get stuck mid-run (e.g. ML service hang past
// its timeout) eventually surface as failed.
const REAP_INTERVAL_MS = 5 * 60 * 1000;
setInterval(() => {
  try {
    const reaped = reapStuckJobs();
    if (reaped > 0) {
      logger.warn({ reaped }, "Periodic reaper marked stuck jobs as failed");
    }
  } catch (error) {
    logger.warn({ error }, "Periodic reaper failed (non-fatal)");
  }
}, REAP_INTERVAL_MS).unref();

// Periodic disk cleanup: delete uploaded videos for completed jobs older than
// VIDEO_RETENTION_DAYS so the uploads directory doesn't grow unbounded.
const VIDEO_RETENTION_DAYS = Number(process.env.VIDEO_RETENTION_DAYS ?? "30");
const CLEANUP_INTERVAL_MS = 6 * 60 * 60 * 1000; // 6 hours
function sweepOldVideos(): void {
  if (!Number.isFinite(VIDEO_RETENTION_DAYS) || VIDEO_RETENTION_DAYS <= 0) {
    return;
  }
  let removed = 0;
  try {
    const candidates = listVideosEligibleForCleanup(VIDEO_RETENTION_DAYS);
    for (const { jobId, filePath } of candidates) {
      try {
        if (filePath && fs.existsSync(filePath)) {
          fs.unlinkSync(filePath);
          removed += 1;
          logger.info({ jobId, filePath }, "Removed expired video file");
        }
      } catch (error) {
        logger.warn({ jobId, filePath, error }, "Failed to remove expired video");
      }
    }
  } catch (error) {
    logger.warn({ error }, "Video retention sweep failed (non-fatal)");
  }
  if (removed > 0) {
    logger.info({ removed, retentionDays: VIDEO_RETENTION_DAYS }, "Video retention sweep complete");
  }
}
sweepOldVideos();
setInterval(sweepOldVideos, CLEANUP_INTERVAL_MS).unref();

// Create Express app
const app: Express = express();

// Enable only when a trusted reverse proxy terminates client traffic.
app.set("trust proxy", config.trustProxy ? 1 : false);

// Security middleware
app.use(
  helmet({
    contentSecurityPolicy: {
      directives: {
        defaultSrc: ["'self'"],
        styleSrc: ["'self'", "'unsafe-inline'"],
        scriptSrc: ["'self'"],
        imgSrc: ["'self'", "data:", "blob:"],
      },
    },
    crossOriginEmbedderPolicy: false,
    crossOriginResourcePolicy: { policy: "cross-origin" },
  }),
);

// Compression middleware
app.use(compression());

// Request ID middleware (must be before logging)
app.use(requestIdMiddleware);

// Structured logging middleware
app.use(
  pinoHttp({
    logger,
    customLogLevel: (_req, res, _err) => {
      if (res.statusCode >= 500) return "error";
      if (res.statusCode >= 400) return "warn";
      return "info";
    },
    customSuccessMessage: (req, _res) => {
      return `${req.method} ${req.url} completed`;
    },
    customErrorMessage: (req, _res, _err) => {
      return `${req.method} ${req.url} failed`;
    },
  }),
);

// CORS configuration
app.use(
  cors({
    origin: (origin, callback) => {
      if (!origin || config.cors.allowedOrigins.includes(origin)) {
        callback(null, true);
      } else {
        callback(new Error("Not allowed by CORS"));
      }
    },
    credentials: true,
    methods: ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allowedHeaders: ["Content-Type", "Authorization", "X-Request-ID"],
  }),
);

// Body parsing middleware. File uploads are handled by multer on /api/upload.
app.use(express.json({ limit: config.body.jsonLimit }));
app.use(express.urlencoded({ extended: true, limit: config.body.jsonLimit }));

const JOB_STATUS_OR_HEALTH_PATH =
  /^\/api\/jobs\/(?:health-check|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$/i;

function isJobStatusPollingRequest(req: Request): boolean {
  const pathWithoutQuery = req.originalUrl.split("?")[0];
  return req.method === "GET" && JOB_STATUS_OR_HEALTH_PATH.test(pathWithoutQuery);
}

// Rate limiting
const limiter = rateLimit({
  windowMs: config.rateLimit.windowMs,
  max: config.rateLimit.maxRequests,
  skip: isJobStatusPollingRequest,
  message: {
    error: "TOO_MANY_REQUESTS",
    message: "Too many requests from this IP, please try again later",
  },
  standardHeaders: true,
  legacyHeaders: false,
});

app.use("/api/", limiter);

// Health check endpoint
app.get("/health", (req, res) => {
  const db = getDatabase();
  const dbHealthy = db ? true : false;

  const health = {
    status: dbHealthy ? "healthy" : "degraded",
    timestamp: new Date().toISOString(),
    uptime: process.uptime(),
    environment: config.env,
    services: {
      database: dbHealthy ? "connected" : "disconnected",
    },
  };

  res.status(dbHealthy ? 200 : 503).json(health);
});

// Readiness check endpoint
app.get("/ready", (req, res) => {
  const db = getDatabase();
  if (!db) {
    return res.status(503).json({
      status: "not ready",
      message: "Database not initialized",
    });
  }
  res.json({ status: "ready" });
});

// Serve static files with access control — block raw video downloads
app.use(
  "/uploads",
  (req, res, next) => {
    // Block access to raw video files
    if (req.path.startsWith("/videos/")) {
      return res.status(403).json({ error: "Access denied" });
    }

    // Only allow known resource directories
    const allowedPrefixes = ["/frames/", "/odometer_images/"];
    if (!allowedPrefixes.some((prefix) => req.path.startsWith(prefix))) {
      return res.status(403).json({ error: "Access denied" });
    }

    next();
  },
  express.static(path.join(process.cwd(), "uploads")),
);

// API routes
app.use("/api/upload", uploadRouter);
app.use("/api/jobs", jobsRouter);
app.use("/api/metrics", metricsRouter);
app.use("/api/inspections", inspectionsRouter);

// 404 handler
app.use(notFoundHandler);

// Global error handler (must be last)
app.use(errorHandler);

// Graceful shutdown handler
const gracefulShutdown = (signal: string) => {
  logger.info(
    { signal },
    "Received shutdown signal, closing server gracefully",
  );

  try {
    const db = getDatabase();
    if (db) {
      db.close();
      logger.info("Database connection closed");
    }
  } catch (error) {
    logger.error({ error }, "Error closing database connection");
  }

  process.exit(0);
};

process.on("SIGTERM", () => gracefulShutdown("SIGTERM"));
process.on("SIGINT", () => gracefulShutdown("SIGINT"));

// Unhandled rejection handler
process.on("unhandledRejection", (reason, promise) => {
  logger.error({ reason, promise }, "Unhandled promise rejection");
});

// Uncaught exception handler
process.on("uncaughtException", (error) => {
  logger.fatal({ error }, "Uncaught exception");
  gracefulShutdown("uncaughtException");
});

// Start server
const _server = app.listen(config.port, () => {
  logger.info(
    {
      port: config.port,
      environment: config.env,
      nodeVersion: process.version,
    },
    "Backend API server started",
  );
});

// Export app for testing
export default app;
