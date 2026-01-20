/**
 * Backend API server entry point
 * Production-ready Express server with security, logging, and error handling
 */

import express, { Express } from "express";
import cors from "cors";
import helmet from "helmet";
import compression from "compression";
import rateLimit from "express-rate-limit";
import pinoHttp from "pino-http";
import path from "path";
import { config } from "./config/env";
import logger from "./utils/logger";
import { initDatabase, getDatabase } from "./db/init";
import { requestIdMiddleware } from "./middleware/requestId";
import { errorHandler, notFoundHandler } from "./middleware/errorHandler";
import uploadRouter from "./routes/upload";
import jobsRouter from "./routes/jobs";
import inspectionsRouter from "./routes/inspections";

// Initialize database
try {
  initDatabase();
  logger.info("Database initialized successfully");
} catch (error) {
  logger.fatal({ error }, "Failed to initialize database");
  process.exit(1);
}

// Create Express app
const app: Express = express();

// Trust proxy for accurate IP addresses behind reverse proxy
app.set("trust proxy", 1);

// Security middleware
app.use(helmet({
  contentSecurityPolicy: {
    directives: {
      defaultSrc: ["'self'"],
      styleSrc: ["'self'", "'unsafe-inline'"],
      scriptSrc: ["'self'"],
      imgSrc: ["'self'", "data:", "blob:"],
    },
  },
  crossOriginEmbedderPolicy: false,
}));

// Compression middleware
app.use(compression());

// Request ID middleware (must be before logging)
app.use(requestIdMiddleware);

// Structured logging middleware
app.use(
  pinoHttp({
    logger,
    customLogLevel: (req, res, err) => {
      if (res.statusCode >= 500) return "error";
      if (res.statusCode >= 400) return "warn";
      return "info";
    },
    customSuccessMessage: (req, res) => {
      return `${req.method} ${req.url} completed`;
    },
    customErrorMessage: (req, res, err) => {
      return `${req.method} ${req.url} failed`;
    },
  })
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
  })
);

// Body parsing middleware
app.use(express.json({ limit: "50mb" }));
app.use(express.urlencoded({ extended: true, limit: "50mb" }));

// Rate limiting
const limiter = rateLimit({
  windowMs: config.rateLimit.windowMs,
  max: config.rateLimit.maxRequests,
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

// Serve static files (uploads directory)
app.use("/uploads", express.static(path.join(process.cwd(), "uploads")));

// API routes
app.use("/api/upload", uploadRouter);
app.use("/api/jobs", jobsRouter);
app.use("/api/inspections", inspectionsRouter);

// 404 handler
app.use(notFoundHandler);

// Global error handler (must be last)
app.use(errorHandler);

// Graceful shutdown handler
const gracefulShutdown = (signal: string) => {
  logger.info({ signal }, "Received shutdown signal, closing server gracefully");
  
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
const server = app.listen(config.port, () => {
  logger.info(
    {
      port: config.port,
      environment: config.env,
      nodeVersion: process.version,
    },
    "Backend API server started"
  );
});

// Export app for testing
export default app;
