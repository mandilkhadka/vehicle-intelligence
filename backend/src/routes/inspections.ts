/**
 * Inspections route handler
 * Handles inspection data queries with validation and error handling
 */

import { Router, Request, Response } from "express";
import { param, query, validationResult } from "express-validator";
import {
  getInspectionById,
  getAllInspections,
} from "../models/inspection";
import { asyncHandler } from "../middleware/errorHandler";
import { CustomError } from "../middleware/errorHandler";
import logger from "../utils/logger";

const router = Router();

/**
 * Strip backend absolute paths and any "uploads/" prefix from a stored
 * file path so the API only ever returns relative paths under uploads/.
 * Tolerates already-relative paths and Windows separators.
 */
function sanitizeUploadPath(p: string): string {
  let normalized = p.replace(/\\/g, "/");
  const idx = normalized.indexOf("/uploads/");
  if (idx >= 0) {
    normalized = normalized.slice(idx + "/uploads/".length);
  } else if (normalized.startsWith("uploads/")) {
    normalized = normalized.slice("uploads/".length);
  } else if (normalized.includes("..") || normalized.startsWith("/")) {
    // Path escapes uploads (e.g. "../../ml-service/..."). Treat as missing.
    return "";
  }
  // Drop known stale paths from old MOCK_MODE runs.
  if (
    normalized.startsWith("frames/sample/") ||
    normalized === "odometer_images/sample.jpg" ||
    normalized === "exhaust/sample.jpg"
  ) {
    return "";
  }
  return normalized;
}

/**
 * GET /api/inspections
 * Get all inspections with optional pagination
 */
router.get(
  "/",
  [
    query("limit")
      .optional()
      .isInt({ min: 1, max: 100 })
      .withMessage("Limit must be between 1 and 100"),
    query("offset")
      .optional()
      .isInt({ min: 0 })
      .withMessage("Offset must be a non-negative integer"),
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

    logger.debug("Fetching all inspections");
    const inspections = getAllInspections();
    
    // Simple pagination (if needed, can be enhanced with database-level pagination)
    const limit = req.query.limit ? parseInt(req.query.limit as string) : undefined;
    const offset = req.query.offset ? parseInt(req.query.offset as string) : 0;
    
    const paginatedInspections = (limit
      ? inspections.slice(offset, offset + limit)
      : inspections.slice(offset)
    ).map((insp) => {
      const out: any = { ...insp };
      if (insp.damage_summary) {
        try {
          const parsed = JSON.parse(insp.damage_summary);
          if (Array.isArray(parsed?.locations)) {
            for (const loc of parsed.locations) {
              if (typeof loc?.frame === "string") loc.frame = sanitizeUploadPath(loc.frame);
              if (typeof loc?.snapshot === "string") loc.snapshot = sanitizeUploadPath(loc.snapshot);
            }
          }
          out.damage_summary = parsed;
        } catch {}
      }
      if (insp.extracted_frames) {
        try {
          const frames = JSON.parse(insp.extracted_frames);
          if (Array.isArray(frames)) out.extracted_frames = frames.map(sanitizeUploadPath);
        } catch {}
      }
      return out;
    });

    res.json({
      data: paginatedInspections,
      total: inspections.length,
      limit: limit || inspections.length,
      offset,
    });
  })
);

/**
 * GET /api/inspections/:id
 * Get inspection by ID
 */
router.get(
  "/:id",
  [
    param("id")
      .isUUID()
      .withMessage("Inspection ID must be a valid UUID"),
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

    const inspectionId = req.params.id;
    logger.debug({ inspectionId }, "Fetching inspection");

    const inspection = getInspectionById(inspectionId);

    if (!inspection) {
      throw new CustomError("Inspection not found", 404, "INSPECTION_NOT_FOUND");
    }

    // Parse JSON fields if they exist
    const result: any = { ...inspection };
    if (typeof result.exhaust_image_path === "string") {
      result.exhaust_image_path = sanitizeUploadPath(result.exhaust_image_path);
    }
    if (typeof result.speedometer_image_path === "string") {
      result.speedometer_image_path = sanitizeUploadPath(result.speedometer_image_path);
    }
    if (inspection.damage_summary) {
      try {
        const parsed = JSON.parse(inspection.damage_summary);
        if (Array.isArray(parsed?.locations)) {
          for (const loc of parsed.locations) {
            if (typeof loc?.frame === "string") {
              loc.frame = sanitizeUploadPath(loc.frame);
            }
            if (typeof loc?.snapshot === "string") {
              loc.snapshot = sanitizeUploadPath(loc.snapshot);
            }
          }
        }
        result.damage_summary = parsed;
      } catch (e) {
        logger.warn({ inspectionId, field: "damage_summary" }, "Failed to parse damage_summary JSON");
      }
    }
    if (inspection.extracted_frames) {
      try {
        const frames = JSON.parse(inspection.extracted_frames);
        result.extracted_frames = Array.isArray(frames)
          ? frames.map((f: string) => (typeof f === "string" ? sanitizeUploadPath(f) : f))
          : frames;
      } catch (e) {
        logger.warn({ inspectionId, field: "extracted_frames" }, "Failed to parse extracted_frames JSON");
      }
    }
    if (inspection.inspection_report) {
      try {
        result.inspection_report = JSON.parse(inspection.inspection_report);
      } catch (e) {
        logger.warn({ inspectionId, field: "inspection_report" }, "Failed to parse inspection_report JSON");
      }
    }

    res.json(result);
  })
);

export default router;
