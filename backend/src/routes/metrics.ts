/**
 * Metrics route handler
 * Provides aggregated inspection metrics for dashboard
 */

import { Router, Request, Response } from "express";
import { query, validationResult } from "express-validator";
import { getInspectionMetrics } from "../models/inspection";
import { asyncHandler, CustomError } from "../middleware/errorHandler";
import logger from "../utils/logger";

const router = Router();

/**
 * Validate date format (YYYY-MM-DD)
 */
const isValidDateFormat = (value: string) => {
  const dateRegex = /^\d{4}-\d{2}-\d{2}$/;
  if (!dateRegex.test(value)) {
    throw new Error("Date must be in YYYY-MM-DD format");
  }
  const date = new Date(value);
  if (isNaN(date.getTime())) {
    throw new Error("Invalid date");
  }
  return true;
};

/**
 * GET /api/inspections/metrics
 * Get aggregated metrics for dashboard
 */
router.get(
  "/",
  [
    query("startDate")
      .exists()
      .withMessage("startDate is required")
      .custom(isValidDateFormat),
    query("endDate")
      .exists()
      .withMessage("endDate is required")
      .custom(isValidDateFormat),
  ],
  asyncHandler(async (req: Request, res: Response) => {
    const errors = validationResult(req);
    if (!errors.isEmpty()) {
      throw new CustomError(
        errors.array()[0].msg,
        400,
        "VALIDATION_ERROR"
      );
    }

    const startDate = req.query.startDate as string;
    const endDate = req.query.endDate as string;

    // Validate date range
    const start = new Date(startDate);
    const end = new Date(endDate);

    if (start > end) {
      throw new CustomError(
        "startDate must be before or equal to endDate",
        400,
        "INVALID_DATE_RANGE"
      );
    }

    // Limit to 1 year maximum
    const oneYear = 365 * 24 * 60 * 60 * 1000;
    if (end.getTime() - start.getTime() > oneYear) {
      throw new CustomError(
        "Date range cannot exceed 1 year",
        400,
        "DATE_RANGE_TOO_LARGE"
      );
    }

    // Prevent future end dates
    const today = new Date();
    today.setHours(23, 59, 59, 999);
    if (end > today) {
      throw new CustomError(
        "endDate cannot be in the future",
        400,
        "FUTURE_DATE_NOT_ALLOWED"
      );
    }

    logger.debug({ startDate, endDate }, "Fetching inspection metrics");

    const metrics = getInspectionMetrics(startDate, endDate);

    res.json(metrics);
  })
);

export default router;
