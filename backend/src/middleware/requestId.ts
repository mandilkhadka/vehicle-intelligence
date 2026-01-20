/**
 * Request ID middleware
 * Adds unique request ID to each request for tracing
 */

import { Request, Response, NextFunction } from "express";
import { v4 as uuidv4 } from "uuid";

declare global {
  namespace Express {
    interface Request {
      id?: string;
    }
  }
}

export const requestIdMiddleware = (req: Request, res: Response, next: NextFunction): void => {
  req.id = req.get("x-request-id") || uuidv4();
  res.setHeader("x-request-id", req.id);
  next();
};
