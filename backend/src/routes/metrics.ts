/**
 * Metrics route handler
 * Provides aggregated inspection metrics for dashboard
 */

import { Router, Request, Response } from "express";
import { z } from "zod";
import { getInspectionMetrics } from "../models/inspection";
import { asyncHandler, CustomError } from "../middleware/errorHandler";
import { parseQuery } from "../utils/validate";
import logger from "../utils/logger";

const router = Router();

const dateSchema = z
  .string({ required_error: "is required" })
  .regex(/^\d{4}-\d{2}-\d{2}$/, "Date must be in YYYY-MM-DD format")
  .refine((value) => !Number.isNaN(new Date(value).getTime()), "Invalid date");

const metricsQuery = z.object({
  startDate: dateSchema,
  endDate: dateSchema,
});

/**
 * GET /api/metrics
 * Get aggregated metrics for dashboard (router is mounted at /api/metrics).
 *
 * Note: metrics aggregate all inspection rows in range, including those from
 * failed/incomplete jobs — there is deliberately no join on job status.
 */
router.get(
  "/",
  asyncHandler(async (req: Request, res: Response) => {
    const { startDate, endDate } = parseQuery(metricsQuery, req.query);

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
