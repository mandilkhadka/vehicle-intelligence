/**
 * Damage-feedback API.
 *
 * POST   /api/inspections/:id/feedback         Record a verdict on a location
 * GET    /api/inspections/:id/feedback         List verdicts for an inspection
 * DELETE /api/inspections/:id/feedback/:fid    Remove a verdict
 * POST   /api/inspections/:id/missing-damage   Report damage the model missed
 * GET    /api/inspections/:id/missing-damage   List missing-damage reports
 * DELETE /api/inspections/:id/missing-damage/:mid
 * GET    /api/feedback/export?since=ISO        Bulk export for training pipelines
 * GET    /api/feedback/review                  Uncertain-detection queue
 */

import { Router, Request, Response } from "express";
import { z } from "zod";
import { asyncHandler, CustomError } from "../middleware/errorHandler";
import {
  createDamageFeedback,
  createMissingDamage,
  deleteDamageFeedback,
  deleteMissingDamage,
  exportFeedbackSince,
  listFeedbackForInspection,
  listMissingForInspection,
  listUncertainDetections,
  type FeedbackVerdict,
} from "../models/feedback";

const router = Router();

const verdictEnum = z.enum([
  "confirmed",
  "wrong_type",
  "false_positive",
  "missed_severity",
]);

const damageTypePattern = /^[a-z0-9_\-]{1,40}$/i;
const severityPattern = /^(low|medium|high)$/i;
const reviewerPattern = /^[\p{L}\p{N} _.\-@]{1,80}$/u;

const feedbackBody = z.object({
  location_index: z.number().int().min(0).max(1000),
  verdict: verdictEnum,
  corrected_type: z.string().regex(damageTypePattern).optional(),
  corrected_severity: z.string().regex(severityPattern).optional(),
  note: z.string().max(500).optional(),
  reviewer: z.string().regex(reviewerPattern).optional(),
});

const missingBody = z.object({
  frame_path: z.string().max(500).optional(),
  bbox: z.array(z.number()).length(4).optional(),
  type: z.string().regex(damageTypePattern).optional(),
  severity: z.string().regex(severityPattern).optional(),
  part: z.string().regex(/^[a-z0-9_]{1,40}$/i).optional(),
  note: z.string().max(500).optional(),
  reviewer: z.string().regex(reviewerPattern).optional(),
});

function parseBody<T extends z.ZodTypeAny>(schema: T, body: unknown): z.infer<T> {
  const result = schema.safeParse(body);
  if (!result.success) {
    const issues = result.error.issues
      .map((i) => `${i.path.join(".")}: ${i.message}`)
      .join("; ");
    throw new CustomError(
      `Invalid request body — ${issues}`,
      400,
      "VALIDATION_ERROR",
    );
  }
  return result.data;
}

router.post(
  "/inspections/:id/feedback",
  asyncHandler(async (req: Request, res: Response) => {
    const body = parseBody(feedbackBody, req.body);
    const record = createDamageFeedback({
      inspectionId: req.params.id,
      locationIndex: body.location_index,
      verdict: body.verdict as FeedbackVerdict,
      correctedType: body.corrected_type,
      correctedSeverity: body.corrected_severity,
      note: body.note,
      reviewer: body.reviewer,
    });
    res.status(201).json(record);
  }),
);

router.get(
  "/inspections/:id/feedback",
  asyncHandler(async (req: Request, res: Response) => {
    res.json(listFeedbackForInspection(req.params.id));
  }),
);

router.delete(
  "/inspections/:id/feedback/:fid",
  asyncHandler(async (req: Request, res: Response) => {
    const removed = deleteDamageFeedback(req.params.fid);
    if (!removed) {
      throw new CustomError("Feedback not found", 404, "NOT_FOUND");
    }
    res.status(204).end();
  }),
);

router.post(
  "/inspections/:id/missing-damage",
  asyncHandler(async (req: Request, res: Response) => {
    const body = parseBody(missingBody, req.body);
    const record = createMissingDamage({
      inspectionId: req.params.id,
      framePath: body.frame_path,
      bbox: body.bbox,
      type: body.type,
      severity: body.severity,
      part: body.part,
      note: body.note,
      reviewer: body.reviewer,
    });
    res.status(201).json(record);
  }),
);

router.get(
  "/inspections/:id/missing-damage",
  asyncHandler(async (req: Request, res: Response) => {
    res.json(listMissingForInspection(req.params.id));
  }),
);

router.delete(
  "/inspections/:id/missing-damage/:mid",
  asyncHandler(async (req: Request, res: Response) => {
    const removed = deleteMissingDamage(req.params.mid);
    if (!removed) {
      throw new CustomError("Missing-damage report not found", 404, "NOT_FOUND");
    }
    res.status(204).end();
  }),
);

router.get(
  "/feedback/export",
  asyncHandler(async (req: Request, res: Response) => {
    const since = typeof req.query.since === "string" ? req.query.since : undefined;
    if (since && Number.isNaN(Date.parse(since))) {
      throw new CustomError(
        "Invalid 'since' parameter — must be ISO timestamp",
        400,
        "VALIDATION_ERROR",
      );
    }
    res.json({
      since: since ?? null,
      generated_at: new Date().toISOString(),
      rows: exportFeedbackSince(since),
    });
  }),
);

router.get(
  "/feedback/review",
  asyncHandler(async (req: Request, res: Response) => {
    const limit = Number.parseInt(String(req.query.limit ?? "100"), 10);
    const clamped = Number.isFinite(limit) ? Math.min(Math.max(limit, 1), 500) : 100;
    res.json({ items: listUncertainDetections(clamped) });
  }),
);

export default router;
