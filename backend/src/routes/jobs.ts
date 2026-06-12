/**
 * Jobs route handler
 * Handles job status queries with validation and error handling
 */

import { Router, Request, Response } from "express";
import { z } from "zod";
import { getJobById } from "../models/inspection";
import { asyncHandler, CustomError } from "../middleware/errorHandler";
import { parseParams } from "../utils/validate";
import logger from "../utils/logger";

const router = Router();

const jobParams = z.object({
  id: z.string().uuid("Job ID must be a valid UUID"),
});

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
  asyncHandler(async (req: Request, res: Response) => {
    const { id: jobId } = parseParams(jobParams, req.params);
    logger.debug({ jobId }, "Fetching job status");

    const job = getJobById(jobId);

    if (!job) {
      throw new CustomError("Job not found", 404, "JOB_NOT_FOUND");
    }

    res.json(job);
  })
);

export default router;
