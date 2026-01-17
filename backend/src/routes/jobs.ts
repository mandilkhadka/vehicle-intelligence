/**
 * Jobs route handler
 * Handles job status queries
 */

import { Router, Request, Response } from "express";
import { getJobById } from "../models/inspection";

const router = Router();

/**
 * GET /api/jobs/:id
 * Get job status by ID
 */
router.get("/:id", (req: Request, res: Response) => {
  try {
    const jobId = req.params.id;
    const job = getJobById(jobId);

    if (!job) {
      return res.status(404).json({ error: "Job not found" });
    }

    res.json(job);
  } catch (error: any) {
    console.error("Get job error:", error);
    res.status(500).json({
      error: "Failed to get job status",
      message: error.message,
    });
  }
});

export default router;
