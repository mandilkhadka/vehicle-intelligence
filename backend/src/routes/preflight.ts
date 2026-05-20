/**
 * Pre-flight upload quality gate.
 *
 * Accepts the same `video` multipart field as /api/upload, writes the file
 * into a short-lived preflight directory, asks the ML service whether it's
 * usable, and returns the verdict. The frontend uses this BEFORE the full
 * upload so users get fast actionable feedback instead of waiting through
 * the heavy inspection pipeline only to discover the clip was unusable.
 *
 * On `can_proceed: false` the temporary file is deleted. On `can_proceed:
 * true` the client should re-upload to /api/upload (we deliberately do not
 * accept the gated file as the canonical upload — the upload route owns
 * file-record creation, virus scanning hooks, etc.).
 */

import { Router, Request, Response, NextFunction } from "express";
import multer from "multer";
import axios from "axios";
import * as fs from "fs";
import * as path from "path";
import { z } from "zod";
import {
  ensureDirectoryExists,
  generateUniqueFilename,
  getUploadPath,
  isValidVideoFormat,
} from "../utils/fileUtils";
import { asyncHandler, CustomError } from "../middleware/errorHandler";
import { config } from "../config/env";
import logger from "../utils/logger";

const router = Router();

const preflightStorage = multer.diskStorage({
  destination: (_req, _file, cb) => {
    const dest = getUploadPath("preflight");
    ensureDirectoryExists(dest);
    cb(null, dest);
  },
  filename: (_req, file, cb) => cb(null, generateUniqueFilename(file.originalname)),
});

const preflightUpload = multer({
  storage: preflightStorage,
  fileFilter: (_req, file, cb) => {
    if (isValidVideoFormat(file.originalname)) cb(null, true);
    else cb(new Error("Invalid file format. Only video files are allowed."));
  },
  // Allow up to the same max as /upload — we want to reject big bad clips before
  // they enter the pipeline rather than block them at the size limit later.
  limits: { fileSize: config.upload.maxSize },
}).single("video");

const preflightResponseSchema = z
  .object({
    ok: z.boolean(),
    can_proceed: z.boolean(),
    duration_sec: z.number().nullable().optional(),
    sampled_frames: z.number().optional(),
    coverage_estimate: z.number().optional(),
    blur_score: z.number().nullable().optional(),
    brightness_score: z.number().nullable().optional(),
    vehicle_visible_ratio: z.number().optional(),
    issues: z.array(z.string()).default([]),
    warnings: z.array(z.string()).default([]),
    elapsed_sec: z.number().optional(),
  })
  .passthrough();

function deleteQuietly(filePath?: string): void {
  if (!filePath) return;
  try {
    if (fs.existsSync(filePath)) fs.unlinkSync(filePath);
  } catch (error) {
    logger.warn({ error, filePath }, "Failed to clean preflight temp file");
  }
}

router.post(
  "/",
  (req: Request, res: Response, next: NextFunction) => {
    preflightUpload(req, res, (err) => {
      if (err) {
        deleteQuietly((req.file as Express.Multer.File | undefined)?.path);
        if (err instanceof multer.MulterError && err.code === "LIMIT_FILE_SIZE") {
          return next(
            new CustomError(
              `File size exceeds maximum allowed size of ${
                config.upload.maxSize / 1024 / 1024
              }MB`,
              400,
              "FILE_TOO_LARGE",
            ),
          );
        }
        return next(
          new CustomError(err.message || "Invalid file format", 400, "FILE_VALIDATION_ERROR"),
        );
      }
      next();
    });
  },
  asyncHandler(async (req: Request, res: Response) => {
    const file = req.file as Express.Multer.File | undefined;
    if (!file) {
      throw new CustomError("No video file uploaded", 400, "NO_VIDEO_FILE");
    }

    const absoluteVideoPath = path.isAbsolute(file.path)
      ? file.path
      : path.join(process.cwd(), file.path);

    try {
      const mlServiceUrl = `${config.mlService.url}/api/preflight`;
      logger.info(
        { mlServiceUrl, videoPath: absoluteVideoPath },
        "Forwarding to ML preflight",
      );

      const response = await axios.post(
        mlServiceUrl,
        { video_path: absoluteVideoPath },
        {
          // Pre-flight is supposed to be fast; cap aggressively so we surface
          // ML hangs as warnings rather than blocking the whole upload.
          timeout: 30000,
          headers: {
            "Content-Type": "application/json",
            ...(config.mlService.apiKey
              ? { "X-Internal-API-Key": config.mlService.apiKey }
              : {}),
          },
          validateStatus: (status) => status < 500,
        },
      );

      if (response.status >= 400) {
        logger.warn(
          { status: response.status, data: response.data },
          "ML preflight returned error",
        );
        // Fail open — if the ML service can't preflight, let the upload through.
        // The full pipeline will reject the clip later if it really is bad.
        deleteQuietly(absoluteVideoPath);
        return res.status(200).json({
          ok: true,
          can_proceed: true,
          issues: [],
          warnings: ["Pre-flight check unavailable; proceeding without quality gate."],
          ml_status: response.status,
        });
      }

      const parsed = preflightResponseSchema.safeParse(response.data);
      if (!parsed.success) {
        logger.warn({ issues: parsed.error.issues }, "Malformed preflight response");
        deleteQuietly(absoluteVideoPath);
        return res.status(200).json({
          ok: true,
          can_proceed: true,
          issues: [],
          warnings: ["Pre-flight response malformed; proceeding without quality gate."],
        });
      }

      // Always delete — the canonical upload happens via /api/upload, not here.
      deleteQuietly(absoluteVideoPath);
      return res.status(200).json(parsed.data);
    } catch (error) {
      logger.warn({ error }, "Pre-flight call failed; degrading open");
      deleteQuietly(absoluteVideoPath);
      // Fail open — infra failures shouldn't block users from trying their upload.
      return res.status(200).json({
        ok: true,
        can_proceed: true,
        issues: [],
        warnings: [
          "Pre-flight check unavailable; proceeding without quality gate.",
        ],
      });
    }
  }),
);

export default router;
