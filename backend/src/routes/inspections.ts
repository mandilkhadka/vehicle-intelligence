/**
 * Inspections route handler
 * Handles inspection data queries with validation and error handling
 */

import { Router, Request, Response } from "express";
import axios from "axios";
import { body, param, query, validationResult } from "express-validator";
import {
  getInspectionById,
  getAllInspections,
  updateInspection,
  type InspectionRecord,
} from "../models/inspection";
import { asyncHandler } from "../middleware/errorHandler";
import { CustomError } from "../middleware/errorHandler";
import { config } from "../config/env";
import logger from "../utils/logger";

const router = Router();

const IDENTITY_FIELDS = [
  "brand",
  "model",
  "year",
  "variant",
  "type",
  "vehicle_category",
  "category",
  "color",
  "vin",
  "registration",
] as const;

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

function bodyString(req: Request, ...fields: string[]): string | undefined {
  for (const field of fields) {
    const value = req.body?.[field];
    if (typeof value !== "string") {
      continue;
    }
    const trimmed = value.trim();
    if (trimmed) {
      return trimmed;
    }
  }
  return undefined;
}

function bodyNumber(req: Request, field: string): number | undefined {
  const value = req.body?.[field];
  if (value === undefined || value === null || value === "") {
    return undefined;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function identityOverrideFromBody(
  req: Request,
): Record<string, unknown> | undefined {
  const override: Record<string, unknown> = {
    source:
      bodyString(req, "source", "vehicle_identity_source") ||
      "manual_review",
    brand: bodyString(req, "brand", "vehicle_brand"),
    model: bodyString(req, "model", "vehicle_model"),
    year: bodyString(req, "year", "vehicle_year"),
    variant: bodyString(req, "variant", "vehicle_variant"),
    type: bodyString(req, "type", "vehicle_type"),
    vehicle_category: bodyString(req, "vehicle_category"),
    category: bodyString(req, "category"),
    color: bodyString(req, "color", "vehicle_color"),
    vin: bodyString(req, "vin"),
    registration: bodyString(req, "registration"),
    confidence: bodyNumber(req, "confidence"),
  };
  const hasEvidence = Object.entries(override).some(
    ([key, value]) =>
      key !== "source" &&
      key !== "confidence" &&
      value !== undefined,
  );
  return hasEvidence ? override : undefined;
}

function parseJsonObject(value: string | undefined): Record<string, unknown> {
  if (!value) {
    return {};
  }
  try {
    const parsed = JSON.parse(value);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed)
      ? parsed
      : {};
  } catch {
    return {};
  }
}

function stringValue(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

function numberValue(value: unknown): number | undefined {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function mergeVehicleIdentityOverride(
  baseInfo: Record<string, unknown>,
  override: Record<string, unknown>,
): Record<string, unknown> {
  const merged: Record<string, unknown> = { ...baseInfo };
  const applied: string[] = [];

  for (const field of IDENTITY_FIELDS) {
    const value = override[field];
    if (value === undefined || value === null) {
      continue;
    }
    if (typeof value === "string" && !value.trim()) {
      continue;
    }
    merged[field] = value;
    applied.push(field);
  }

  const source = stringValue(override.source) || "manual_review";
  merged.identity_source = source;
  if (applied.length > 0) {
    merged.identity_override_fields = applied;
    merged.identity_notes = `Exact identity fields merged from ${source}; video-derived fields remain candidates where not overridden.`;
  }

  const overrideConfidence = numberValue(override.confidence);
  const baseConfidence = numberValue(merged.confidence) || 0;
  merged.confidence = Math.max(
    baseConfidence,
    overrideConfidence ?? (applied.length > 0 ? 0.95 : 0),
  );
  return merged;
}

function buildIdentityUpdate(
  inspection: InspectionRecord,
  override: Record<string, unknown>,
): Partial<InspectionRecord> {
  const vehicleInfo = mergeVehicleIdentityOverride(
    parseJsonObject(inspection.vehicle_info),
    override,
  );
  const report = parseJsonObject(inspection.inspection_report);
  const reportVehicleDetails =
    report.vehicle_details &&
    typeof report.vehicle_details === "object" &&
    !Array.isArray(report.vehicle_details)
      ? (report.vehicle_details as Record<string, unknown>)
      : {};
  report.vehicle_details = {
    ...reportVehicleDetails,
    ...vehicleInfo,
  };
  delete report.pipeline_audit;

  return {
    vehicle_type: stringValue(vehicleInfo.type),
    vehicle_brand: stringValue(vehicleInfo.brand),
    vehicle_model: stringValue(vehicleInfo.model),
    vehicle_year: stringValue(vehicleInfo.year),
    vehicle_variant: stringValue(vehicleInfo.variant),
    vehicle_confidence: numberValue(vehicleInfo.confidence),
    vehicle_info: JSON.stringify(vehicleInfo),
    inspection_report: JSON.stringify(report),
  };
}

function validateVlmResult(value: unknown): Record<string, unknown> | undefined {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return undefined;
  }
  const result = value as Record<string, unknown>;
  if (typeof result.available !== "boolean") {
    return undefined;
  }
  if (result.available && (!result.vehicle || typeof result.vehicle !== "object" || Array.isArray(result.vehicle))) {
    return undefined;
  }
  return result;
}

function mergeVehicleInfoFromVlm(
  baseInfo: Record<string, unknown>,
  vlmResult: Record<string, unknown>,
): Record<string, unknown> {
  if (!vlmResult.available || !vlmResult.vehicle || typeof vlmResult.vehicle !== "object") {
    return { ...baseInfo };
  }
  const vehicle = vlmResult.vehicle as Record<string, unknown>;
  const merged: Record<string, unknown> = { ...baseInfo };
  for (const field of [
    "type",
    "brand",
    "model",
    "year",
    "variant",
    "vehicle_category",
    "category",
    "color",
    "generation",
  ]) {
    const value = vehicle[field];
    if (typeof value === "string" && !value.trim()) {
      continue;
    }
    if (value !== undefined && value !== null) {
      merged[field] = value;
    }
  }
  const baseConfidence = numberValue(merged.confidence) || 0;
  const vlmConfidence = numberValue(vehicle.confidence) || 0;
  merged.confidence = Math.max(baseConfidence, vlmConfidence);
  return merged;
}

function buildVlmUpdate(
  inspection: InspectionRecord,
  vlmResult: Record<string, unknown>,
): Partial<InspectionRecord> {
  const vehicleInfo = mergeVehicleInfoFromVlm(
    parseJsonObject(inspection.vehicle_info),
    vlmResult,
  );
  const report = parseJsonObject(inspection.inspection_report);
  const reportVehicleDetails =
    report.vehicle_details &&
    typeof report.vehicle_details === "object" &&
    !Array.isArray(report.vehicle_details)
      ? (report.vehicle_details as Record<string, unknown>)
      : {};
  report.gemini_analysis = vlmResult;
  report.visual_analysis = {
    available: Boolean(vlmResult.available),
    reason: vlmResult.reason,
    provider: vlmResult.provider,
  };
  report.vehicle_details = {
    ...reportVehicleDetails,
    ...vehicleInfo,
  };
  delete report.pipeline_audit;

  return {
    vehicle_type: stringValue(vehicleInfo.type),
    vehicle_brand: stringValue(vehicleInfo.brand),
    vehicle_model: stringValue(vehicleInfo.model),
    vehicle_year: stringValue(vehicleInfo.year),
    vehicle_variant: stringValue(vehicleInfo.variant),
    vehicle_confidence: numberValue(vehicleInfo.confidence),
    vehicle_info: JSON.stringify(vehicleInfo),
    inspection_report: JSON.stringify(report),
  };
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
      const out: Record<string, unknown> = { ...insp };
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
        } catch (e) {
          logger.warn({ error: e, field: "damage_summary", inspectionId: insp.id }, "Failed to parse damage_summary JSON");
        }
      }
      if (insp.extracted_frames) {
        try {
          const frames = JSON.parse(insp.extracted_frames);
          if (Array.isArray(frames)) out.extracted_frames = frames.map(sanitizeUploadPath);
        } catch (e) {
          logger.warn({ error: e, field: "extracted_frames", inspectionId: insp.id }, "Failed to parse extracted_frames JSON");
        }
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
 * PUT /api/inspections/:id/identity
 * Merge trusted identity evidence into an existing inspection.
 */
router.put(
  "/:id/identity",
  [
    param("id")
      .isUUID()
      .withMessage("Inspection ID must be a valid UUID"),
    ...[
      "source",
      "vehicle_identity_source",
      "brand",
      "vehicle_brand",
      "model",
      "vehicle_model",
      "year",
      "vehicle_year",
      "variant",
      "vehicle_variant",
      "type",
      "vehicle_type",
      "vehicle_category",
      "category",
      "color",
      "vehicle_color",
      "vin",
      "registration",
    ].map((fieldName) =>
      body(fieldName)
        .optional({ nullable: true })
        .isString()
        .isLength({ max: 200 })
        .withMessage(`${fieldName} must be a string up to 200 characters`),
    ),
    body("confidence")
      .optional({ nullable: true })
      .isFloat({ min: 0, max: 1 })
      .withMessage("confidence must be between 0 and 1"),
  ],
  asyncHandler(async (req: Request, res: Response) => {
    const errors = validationResult(req);
    if (!errors.isEmpty()) {
      throw new CustomError(
        errors.array()[0].msg,
        400,
        "VALIDATION_ERROR",
      );
    }

    const inspectionId = req.params.id;
    const inspection = getInspectionById(inspectionId);
    if (!inspection) {
      throw new CustomError("Inspection not found", 404, "INSPECTION_NOT_FOUND");
    }

    const override = identityOverrideFromBody(req);
    if (!override) {
      throw new CustomError(
        "At least one identity evidence field is required",
        400,
        "IDENTITY_EVIDENCE_REQUIRED",
      );
    }

    const updated = updateInspection(
      inspectionId,
      buildIdentityUpdate(inspection, override),
    );
    logger.info(
      {
        inspectionId,
        source: override.source,
        fields: parseJsonObject(updated.vehicle_info).identity_override_fields,
      },
      "Merged trusted identity evidence into inspection",
    );

    res.json({
      data: {
        ...updated,
        vehicle_info: parseJsonObject(updated.vehicle_info),
        inspection_report: parseJsonObject(updated.inspection_report),
      },
    });
  }),
);

/**
 * PUT /api/inspections/:id/vlm
 * Merge externally generated VLM evidence into an existing inspection.
 */
router.put(
  "/:id/vlm",
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
        "VALIDATION_ERROR",
      );
    }

    const inspectionId = req.params.id;
    const inspection = getInspectionById(inspectionId);
    if (!inspection) {
      throw new CustomError("Inspection not found", 404, "INSPECTION_NOT_FOUND");
    }

    const vlmResult = validateVlmResult(req.body);
    if (!vlmResult) {
      throw new CustomError(
        "VLM evidence must include boolean available and a vehicle object when available is true",
        400,
        "INVALID_VLM_EVIDENCE",
      );
    }

    const updated = updateInspection(
      inspectionId,
      buildVlmUpdate(inspection, vlmResult),
    );
    logger.info(
      {
        inspectionId,
        provider: vlmResult.provider,
        available: vlmResult.available,
      },
      "Merged external VLM evidence into inspection",
    );

    res.json({
      data: {
        ...updated,
        vehicle_info: parseJsonObject(updated.vehicle_info),
        inspection_report: parseJsonObject(updated.inspection_report),
      },
    });
  }),
);

/**
 * POST /api/inspections/:id/retry-vlm
 * Rerun VLM analysis against saved organized frames after keys/quota are fixed.
 */
router.post(
  "/:id/retry-vlm",
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
        "VALIDATION_ERROR",
      );
    }

    const inspectionId = req.params.id;
    const inspection = getInspectionById(inspectionId);
    if (!inspection) {
      throw new CustomError("Inspection not found", 404, "INSPECTION_NOT_FOUND");
    }

    const report = parseJsonObject(inspection.inspection_report);
    const vehicleInfo = parseJsonObject(inspection.vehicle_info);
    const frameAnalysis =
      report.frame_analysis &&
      typeof report.frame_analysis === "object" &&
      !Array.isArray(report.frame_analysis)
        ? (report.frame_analysis as Record<string, unknown>)
        : undefined;
    if (!frameAnalysis) {
      throw new CustomError(
        "Inspection has no organized frame analysis to retry VLM",
        400,
        "FRAME_ANALYSIS_REQUIRED",
      );
    }

    const retryUrl = `${config.mlService.url}/api/retry-vlm`;
    let mlResponse;
    try {
      mlResponse = await axios.post(
        retryUrl,
        {
          inspection_id: inspectionId,
          frame_analysis: frameAnalysis,
          vehicle_info: vehicleInfo,
          report,
        },
        {
          timeout: config.mlService.timeout,
          headers: config.mlService.apiKey
            ? { "X-Internal-API-Key": config.mlService.apiKey }
            : undefined,
        },
      );
    } catch (error: unknown) {
      const message = axios.isAxiosError(error)
        ? error.response?.data?.detail || error.message
        : error instanceof Error
          ? error.message
          : "Unknown ML service error";
      throw new CustomError(
        `Failed to retry VLM analysis: ${message}`,
        502,
        "VLM_RETRY_FAILED",
      );
    }

    const vlmResult = validateVlmResult(mlResponse.data?.gemini_analysis);
    if (!vlmResult) {
      throw new CustomError(
        "ML service returned invalid VLM evidence",
        502,
        "INVALID_VLM_EVIDENCE",
      );
    }

    const updated = updateInspection(
      inspectionId,
      buildVlmUpdate(inspection, vlmResult),
    );
    logger.info(
      {
        inspectionId,
        provider: vlmResult.provider,
        available: vlmResult.available,
      },
      "Retried and merged VLM evidence into inspection",
    );

    res.json({
      data: {
        ...updated,
        vehicle_info: parseJsonObject(updated.vehicle_info),
        inspection_report: parseJsonObject(updated.inspection_report),
      },
    });
  }),
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
    const result: Record<string, unknown> = { ...inspection };
    if (typeof result.exhaust_image_path === "string") {
      result.exhaust_image_path = sanitizeUploadPath(result.exhaust_image_path);
    }
    if (typeof result.speedometer_image_path === "string") {
      result.speedometer_image_path = sanitizeUploadPath(result.speedometer_image_path);
    }
    if (inspection.odometer_info) {
      try {
        const parsed = JSON.parse(inspection.odometer_info) as Record<string, unknown>;
        for (const key of ["speedometer_image_path", "source_frame_path", "organized_frame_path", "crop_path", "readout_crop_path"]) {
          if (typeof parsed?.[key] === "string") {
            parsed[key] = sanitizeUploadPath(parsed[key]);
          }
        }
        result.odometer_info = parsed;
      } catch (e) {
        logger.warn({ inspectionId, field: "odometer_info" }, "Failed to parse odometer_info JSON");
      }
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
