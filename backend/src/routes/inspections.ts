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
    
    const paginatedInspections = limit 
      ? inspections.slice(offset, offset + limit)
      : inspections.slice(offset);

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
    if (inspection.damage_summary) {
      try {
        result.damage_summary = JSON.parse(inspection.damage_summary);
      } catch (e) {
        logger.warn({ inspectionId, field: "damage_summary" }, "Failed to parse damage_summary JSON");
      }
    }
    if (inspection.extracted_frames) {
      try {
        result.extracted_frames = JSON.parse(inspection.extracted_frames);
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
