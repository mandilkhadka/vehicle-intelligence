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
  DATABASE_PATH: z.string().optional(),
  UPLOAD_MAX_SIZE: z.string().transform(Number).pipe(z.number().int().positive()).default("524288000"),
  RATE_LIMIT_WINDOW_MS: z.string().transform(Number).pipe(z.number().int().positive()).default("900000"),
  RATE_LIMIT_MAX_REQUESTS: z.string().transform(Number).pipe(z.number().int().positive()).default("100"),
  LOG_LEVEL: z.enum(["fatal", "error", "warn", "info", "debug", "trace"]).default("info"),
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

export const config = {
  env: env.NODE_ENV,
  port: env.PORT,
  cors: {
    allowedOrigins: env.CORS_ALLOWED_ORIGINS.split(",").map((origin) => origin.trim()),
  },
  mlService: {
    url: env.ML_SERVICE_URL,
    timeout: 300000, // 5 minutes for video processing
  },
  database: {
    path: env.DATABASE_PATH || "vehicle_intelligence.db",
  },
  upload: {
    maxSize: env.UPLOAD_MAX_SIZE,
    allowedVideoTypes: ["video/mp4", "video/quicktime", "video/x-msvideo", "video/x-matroska"],
    allowedImageTypes: ["image/jpeg", "image/png", "image/heic", "image/webp"],
  },
  rateLimit: {
    windowMs: env.RATE_LIMIT_WINDOW_MS,
    maxRequests: env.RATE_LIMIT_MAX_REQUESTS,
  },
  logging: {
    level: env.LOG_LEVEL,
    pretty: env.NODE_ENV === "development",
  },
} as const;

export default config;
