/**
 * Global error handling middleware
 * Provides consistent error responses and logging
 */

import { Request, Response, NextFunction } from "express";
import { validationResult } from "express-validator";
import logger from "../utils/logger";
import { config } from "../config/env";

export interface AppError extends Error {
  statusCode?: number;
  code?: string;
  isOperational?: boolean;
}

export class CustomError extends Error implements AppError {
  statusCode: number;
  code: string;
  isOperational: boolean;

  constructor(message: string, statusCode: number = 500, code: string = "INTERNAL_ERROR") {
    super(message);
    this.statusCode = statusCode;
    this.code = code;
    this.isOperational = true;
    Error.captureStackTrace(this, this.constructor);
  }
}

/**
 * Throw a 400 CustomError if express-validator found any invalid fields.
 * Call at the top of a handler after its validation chain ran.
 */
export function assertValid(req: Request): void {
  const errors = validationResult(req);
  if (!errors.isEmpty()) {
    throw new CustomError(errors.array()[0].msg, 400, "VALIDATION_ERROR");
  }
}

export const errorHandler = (
  err: AppError,
  req: Request,
  res: Response,
  _next: NextFunction
): void => {
  const statusCode = err.statusCode || 500;
  const code = err.code || "INTERNAL_ERROR";
  const message = err.message || "Internal server error";

  // Log error details
  const logContext = {
    error: {
      message,
      code,
      stack: config.env === "development" ? err.stack : undefined,
    },
    request: {
      method: req.method,
      url: req.url,
      ip: req.ip,
      userAgent: req.get("user-agent"),
    },
  };

  if (statusCode >= 500) {
    logger.error(logContext, "Server error occurred");
  } else {
    logger.warn(logContext, "Client error occurred");
  }

  // Send standardized error response
  res.status(statusCode).json({
    success: false,
    error: {
      code,
      message,
      ...(config.env === "development" && { details: err.stack }),
    },
    timestamp: new Date().toISOString(),
    path: req.path,
  });
};

export const notFoundHandler = (req: Request, res: Response, next: NextFunction): void => {
  const error = new CustomError(`Route ${req.method} ${req.path} not found`, 404, "NOT_FOUND");
  next(error);
};

export const asyncHandler = (
  fn: (req: Request, res: Response, next: NextFunction) => Promise<unknown>
) => {
  return (req: Request, res: Response, next: NextFunction) => {
    Promise.resolve(fn(req, res, next)).catch(next);
  };
};
