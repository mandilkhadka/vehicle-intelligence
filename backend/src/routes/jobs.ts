/**
 * Jobs route handler
 * Handles job status queries with validation and error handling
 */

import { Router, Request, Response } from "express";
import { param } from "express-validator";
import { getJobById } from "../models/inspection";
import { asyncHandler, assertValid, CustomError } from "../middleware/errorHandler";
import logger from "../utils/logger";

const router = Router();

/**
 * GET /api/jobs/health-check
 * Lightweight health endpoint used by local service startup checks.
 */
router.get("/health-check", (_req: Request, res: Response) => {
  res.json({ status: "ok" });
});

/**
 * GET /api/jobs/:id
 * Get job status by ID
 */
router.get(
  "/:id",
  [
    param("id")
      .isUUID()
      .withMessage("Job ID must be a valid UUID"),
  ],
  asyncHandler(async (req: Request, res: Response) => {
    assertValid(req);

    const jobId = req.params.id;
    logger.debug({ jobId }, "Fetching job status");

    const job = getJobById(jobId);

    if (!job) {
      throw new CustomError("Job not found", 404, "JOB_NOT_FOUND");
    }

    res.json(job);
  })
);

export default router;
