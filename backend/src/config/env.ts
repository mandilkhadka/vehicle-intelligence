/**
 * Environment configuration and validation
 * Ensures all required environment variables are present
 */

import { z } from "zod";
import dotenv from "dotenv";

dotenv.config();

const envSchema = z.object({
  NODE_ENV: z.enum(["development", "production", "test"]).default("development"),
  PORT: z.string().transform(Number).pipe(z.number().int().positive()).default("3001"),
  CORS_ALLOWED_ORIGINS: z.string().default("http://localhost:3000,http://localhost:3001"),
  ML_SERVICE_URL: z.string().url().default("http://localhost:8000"),
  ML_SERVICE_API_KEY: z.string().optional(),
  DATABASE_PATH: z.string().optional(),
  UPLOAD_MAX_SIZE: z.string().transform(Number).pipe(z.number().int().positive()).default("524288000"),
  JSON_BODY_LIMIT: z.string().default("1mb"),
  RATE_LIMIT_WINDOW_MS: z.string().transform(Number).pipe(z.number().int().positive()).default("900000"),
  RATE_LIMIT_MAX_REQUESTS: z.string().transform(Number).pipe(z.number().int().positive()).default("100"),
  TRUST_PROXY: z
    .string()
    .transform((value) => ["1", "true", "yes"].includes(value.toLowerCase()))
    .default("false"),
  LOG_LEVEL: z.enum(["fatal", "error", "warn", "info", "debug", "trace"]).default("info"),
  ML_SERVICE_TIMEOUT_MS: z
    .string()
    .transform(Number)
    .pipe(z.number().int().positive())
    .default("600000"),
});

type EnvConfig = z.infer<typeof envSchema>;

let env: EnvConfig;

try {
  env = envSchema.parse(process.env);
} catch (error) {
  if (error instanceof z.ZodError) {
    console.error("❌ Invalid environment configuration:");
    error.errors.forEach((err) => {
      console.error(`  ${err.path.join(".")}: ${err.message}`);
    });
    process.exit(1);
  }
  throw error;
}

const allowedOrigins = env.CORS_ALLOWED_ORIGINS.split(",")
  .map((origin) => origin.trim())
  .filter(Boolean);

if (env.NODE_ENV === "production") {
  if (allowedOrigins.length === 0 || allowedOrigins.includes("*")) {
    console.error(
      "Invalid production CORS configuration: set explicit CORS_ALLOWED_ORIGINS and do not use '*'.",
    );
    process.exit(1);
  }

  if (!env.ML_SERVICE_API_KEY || env.ML_SERVICE_API_KEY.length < 32) {
    console.error(
      "Invalid production ML service configuration: ML_SERVICE_API_KEY must be at least 32 characters.",
    );
    process.exit(1);
  }
}

export const config = {
  env: env.NODE_ENV,
  port: env.PORT,
  cors: {
    allowedOrigins,
  },
  mlService: {
    url: env.ML_SERVICE_URL,
    // Outer HTTP timeout. Must exceed the ML service's per-stage timeout
    // budget so a slow Gemini call doesn't get killed by the network layer
    // and the partial-results path in process.py can return.
    timeout: env.ML_SERVICE_TIMEOUT_MS,
    apiKey: env.ML_SERVICE_API_KEY,
  },
  database: {
    path: env.DATABASE_PATH || "vehicle_intelligence.db",
  },
  upload: {
    maxSize: env.UPLOAD_MAX_SIZE,
    allowedVideoTypes: ["video/mp4", "video/quicktime", "video/x-msvideo", "video/x-matroska"],
    allowedImageTypes: ["image/jpeg", "image/png", "image/heic", "image/webp"],
  },
  body: {
    jsonLimit: env.JSON_BODY_LIMIT,
  },
  rateLimit: {
    windowMs: env.RATE_LIMIT_WINDOW_MS,
    maxRequests: env.RATE_LIMIT_MAX_REQUESTS,
  },
  trustProxy: env.TRUST_PROXY,
  logging: {
    level: env.LOG_LEVEL,
    pretty: env.NODE_ENV === "development",
  },
} as const;

export default config;
