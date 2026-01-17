/**
 * Inspections route handler
 * Handles inspection data queries
 */

import { Router, Request, Response } from "express";
import {
  getInspectionById,
  getAllInspections,
} from "../models/inspection";

const router = Router();

/**
 * GET /api/inspections
 * Get all inspections
 */
router.get("/", (req: Request, res: Response) => {
  try {
    const inspections = getAllInspections();
    res.json(inspections);
  } catch (error: any) {
    console.error("Get inspections error:", error);
    res.status(500).json({
      error: "Failed to get inspections",
      message: error.message,
    });
  }
});

/**
 * GET /api/inspections/:id
 * Get inspection by ID
 */
router.get("/:id", (req: Request, res: Response) => {
  try {
    const inspectionId = req.params.id;
    const inspection = getInspectionById(inspectionId);

    if (!inspection) {
      return res.status(404).json({ error: "Inspection not found" });
    }

    // Parse JSON fields if they exist
    const result: any = { ...inspection };
    if (inspection.damage_summary) {
      try {
        result.damage_summary = JSON.parse(inspection.damage_summary);
      } catch (e) {
        // Keep as string if parsing fails
      }
    }
    if (inspection.extracted_frames) {
      try {
        result.extracted_frames = JSON.parse(inspection.extracted_frames);
      } catch (e) {
        // Keep as string if parsing fails
      }
    }
    if (inspection.inspection_report) {
      try {
        result.inspection_report = JSON.parse(inspection.inspection_report);
      } catch (e) {
        // Keep as string if parsing fails
      }
    }

    res.json(result);
  } catch (error: any) {
    console.error("Get inspection error:", error);
    res.status(500).json({
      error: "Failed to get inspection",
      message: error.message,
    });
  }
});

export default router;
