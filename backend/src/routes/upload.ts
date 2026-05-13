/**
 * Upload route handler
 * Handles video file uploads
 */

import { Router, Request, Response, NextFunction } from "express";
import multer from "multer";
import * as fs from "fs";
import { v4 as uuidv4 } from "uuid";
import { createFile, createJob, updateJobStatus } from "../models/inspection";
import {
  ensureDirectoryExists,
  generateUniqueFilename,
  getFileExtension,
  isValidVideoFormat,
  isValidImageFormat,
  getUploadPath,
} from "../utils/fileUtils";
import { processVideoJob } from "../services/job_processor";
import { asyncHandler } from "../middleware/errorHandler";
import { CustomError } from "../middleware/errorHandler";
import { config } from "../config/env";
import logger from "../utils/logger";

const router = Router();

// File filter to only accept video files
const fileFilter = (
  req: Request,
  file: Express.Multer.File,
  cb: multer.FileFilterCallback,
) => {
  if (isValidVideoFormat(file.originalname)) {
    cb(null, true);
  } else {
    cb(new Error("Invalid file format. Only video files are allowed."));
  }
};

// File filter for images
const imageFileFilter = (
  req: Request,
  file: Express.Multer.File,
  cb: multer.FileFilterCallback,
) => {
  if (isValidImageFormat(file.originalname)) {
    cb(null, true);
  } else {
    cb(new Error("Invalid file format. Only image files are allowed."));
  }
};

// Custom storage that handles different field names
const multiStorage = multer.diskStorage({
  destination: (req, file, cb) => {
    // Use different storage based on field name
    if (file.fieldname === "odometer_image") {
      const uploadPath = getUploadPath("odometer_images");
      ensureDirectoryExists(uploadPath);
      cb(null, uploadPath);
    } else {
      const uploadPath = getUploadPath("videos");
      ensureDirectoryExists(uploadPath);
      cb(null, uploadPath);
    }
  },
  filename: (req, file, cb) => {
    const uniqueFilename = generateUniqueFilename(file.originalname);
    cb(null, uniqueFilename);
  },
});

// Custom file filter that handles different field names
const multiFileFilter = (
  req: Request,
  file: Express.Multer.File,
  cb: multer.FileFilterCallback,
) => {
  if (file.fieldname === "odometer_image") {
    imageFileFilter(req, file, cb);
  } else if (file.fieldname === "video") {
    fileFilter(req, file, cb);
  } else {
    cb(new Error(`Unexpected field name: ${file.fieldname}`));
  }
};

const uploadWithOdometer = multer({
  storage: multiStorage,
  fileFilter: multiFileFilter,
  limits: {
    fileSize: config.upload.maxSize,
  },
}).fields([
  { name: "video", maxCount: 1 },
  { name: "odometer_image", maxCount: 1 },
]);

function bodyString(req: Request, field: string): string | undefined {
  const value = req.body?.[field];
  if (typeof value !== "string") {
    return undefined;
  }
  const trimmed = value.trim();
  return trimmed ? trimmed : undefined;
}

function vehicleIdentityOverrideFromBody(
  req: Request,
): Record<string, unknown> | undefined {
  const override = {
    source: bodyString(req, "vehicle_identity_source") || "upload_form",
    brand: bodyString(req, "vehicle_brand"),
    model: bodyString(req, "vehicle_model"),
    year: bodyString(req, "vehicle_year"),
    variant: bodyString(req, "vehicle_variant"),
    type: bodyString(req, "vehicle_type"),
    vehicle_category: bodyString(req, "vehicle_category"),
    vin: bodyString(req, "vin"),
    registration: bodyString(req, "registration"),
  };
  const hasEvidence = Object.entries(override).some(
    ([key, value]) => key !== "source" && value !== undefined,
  );
  return hasEvidence ? override : undefined;
}

function readHeader(filePath: string, bytes = 64): Buffer {
  const fd = fs.openSync(filePath, "r");
  try {
    const buffer = Buffer.alloc(bytes);
    const bytesRead = fs.readSync(fd, buffer, 0, bytes, 0);
    return buffer.subarray(0, bytesRead);
  } finally {
    fs.closeSync(fd);
  }
}

function hasIsoBmffBrand(header: Buffer, brands: string[]): boolean {
  if (header.length < 12 || header.toString("ascii", 4, 8) !== "ftyp") {
    return false;
  }
  const brandArea = header.toString("ascii", 8, Math.min(header.length, 64));
  return brands.some((brand) => brandArea.includes(brand));
}

function isValidVideoContent(filePath: string, originalName: string): boolean {
  const header = readHeader(filePath);
  const ext = getFileExtension(originalName);

  if ((ext === ".mp4" || ext === ".mov") && hasIsoBmffBrand(header, ["isom", "iso2", "avc1", "mp41", "mp42", "qt  "])) {
    return true;
  }
  if (
    ext === ".avi" &&
    header.length >= 12 &&
    header.toString("ascii", 0, 4) === "RIFF" &&
    header.toString("ascii", 8, 12) === "AVI "
  ) {
    return true;
  }
  if (
    ext === ".mkv" &&
    header.length >= 4 &&
    header[0] === 0x1a &&
    header[1] === 0x45 &&
    header[2] === 0xdf &&
    header[3] === 0xa3
  ) {
    return true;
  }

  return false;
}

function isValidImageContent(filePath: string, originalName: string): boolean {
  const header = readHeader(filePath);
  const ext = getFileExtension(originalName);

  if ((ext === ".jpg" || ext === ".jpeg") && header.length >= 3) {
    return header[0] === 0xff && header[1] === 0xd8 && header[2] === 0xff;
  }
  if (ext === ".png" && header.length >= 8) {
    return header.subarray(0, 8).equals(Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]));
  }
  if (
    ext === ".webp" &&
    header.length >= 12 &&
    header.toString("ascii", 0, 4) === "RIFF" &&
    header.toString("ascii", 8, 12) === "WEBP"
  ) {
    return true;
  }
  if (ext === ".heic") {
    return hasIsoBmffBrand(header, ["heic", "heix", "hevc", "hevx", "mif1", "msf1"]);
  }

  return false;
}

function removeUploadedFile(file?: Express.Multer.File): void {
  if (!file) {
    return;
  }
  try {
    fs.unlinkSync(file.path);
  } catch (error) {
    logger.warn({ error, path: file.path }, "Failed to remove rejected upload");
  }
}

function cleanupUploadedFiles(files?: { [fieldname: string]: Express.Multer.File[] }): void {
  if (!files) {
    return;
  }
  for (const fieldFiles of Object.values(files)) {
    for (const file of fieldFiles) {
      removeUploadedFile(file);
    }
  }
}

/**
 * POST /api/upload
 * Upload a video file and optional odometer image, then create a processing job
 */
router.post(
  "/",
  (req: Request, res: Response, next: NextFunction) => {
    uploadWithOdometer(req, res, (err) => {
      if (err) {
        cleanupUploadedFiles(
          req.files as { [fieldname: string]: Express.Multer.File[] },
        );
        // Handle multer errors
        if (err instanceof multer.MulterError) {
          if (err.code === "LIMIT_FILE_SIZE") {
            return next(
              new CustomError(
                `File size exceeds maximum allowed size of ${config.upload.maxSize / 1024 / 1024}MB`,
                400,
                "FILE_TOO_LARGE",
              ),
            );
          }
          if (err.code === "LIMIT_UNEXPECTED_FILE") {
            return next(
              new CustomError("Invalid file field", 400, "INVALID_FILE_FIELD"),
            );
          }
          return next(
            new CustomError(
              `Upload error: ${err.message}`,
              400,
              "UPLOAD_ERROR",
            ),
          );
        }
        // Handle file filter errors
        return next(
          new CustomError(
            err.message || "Invalid file format",
            400,
            "FILE_VALIDATION_ERROR",
          ),
        );
      }
      next();
    });
  },
  asyncHandler(async (req: Request, res: Response) => {
    const files = req.files as { [fieldname: string]: Express.Multer.File[] };

    // Check if video was uploaded
    if (!files || !files.video || !files.video[0]) {
      cleanupUploadedFiles(files);
      throw new CustomError("No video file uploaded", 400, "NO_VIDEO_FILE");
    }

    const videoFile = files.video[0];
    const odometerImageFile = files.odometer_image?.[0];

    logger.info(
      {
        videoFilename: videoFile.originalname,
        videoSize: videoFile.size,
        videoMimeType: videoFile.mimetype,
        hasOdometerImage: !!odometerImageFile,
      },
      "Processing video upload",
    );

    // Validate odometer image if provided
    if (
      odometerImageFile &&
      !isValidImageFormat(odometerImageFile.originalname)
    ) {
      cleanupUploadedFiles(files);
      throw new CustomError(
        "Invalid odometer image format. Supported: JPG, PNG, HEIC, WEBP",
        400,
        "INVALID_IMAGE_FORMAT",
      );
    }
    if (
      odometerImageFile &&
      !isValidImageContent(odometerImageFile.path, odometerImageFile.originalname)
    ) {
      cleanupUploadedFiles(files);
      throw new CustomError(
        "Invalid odometer image content",
        400,
        "INVALID_IMAGE_CONTENT",
      );
    }

    // Validate video MIME type or extension
    logger.debug(
      {
        videoMimeType: videoFile.mimetype,
        allowedTypes: config.upload.allowedVideoTypes,
      },
      "Checking video MIME type",
    );
    const isKnownMimeType = (
      config.upload.allowedVideoTypes as readonly string[]
    ).includes(videoFile.mimetype);
    const isOctetStream = videoFile.mimetype === "application/octet-stream";
    const validExtension = isValidVideoFormat(videoFile.originalname);

    if (isKnownMimeType) {
      // Known video MIME type — accept
    } else if (isOctetStream && validExtension) {
      // Generic MIME but valid video extension — accept
      logger.debug(
        { filename: videoFile.originalname },
        "Accepting octet-stream with valid video extension",
      );
    } else {
      cleanupUploadedFiles(files);
      throw new CustomError(
        `Invalid video format. Received: ${videoFile.mimetype}. Allowed types: ${config.upload.allowedVideoTypes.join(", ")}`,
        400,
        "INVALID_VIDEO_FORMAT",
      );
    }
    if (!isValidVideoContent(videoFile.path, videoFile.originalname)) {
      cleanupUploadedFiles(files);
      throw new CustomError(
        "Invalid video content",
        400,
        "INVALID_VIDEO_CONTENT",
      );
    }

    // Generate IDs
    const fileId = uuidv4();
    const jobId = uuidv4();

    // Create file record in database
    const fileRecord = createFile({
      id: fileId,
      filename: videoFile.filename,
      original_filename: videoFile.originalname,
      file_path: videoFile.path,
      file_size: videoFile.size,
      mime_type: videoFile.mimetype,
    });

    // Create job record
    const jobRecord = createJob({
      id: jobId,
      file_id: fileId,
      status: "pending",
    });

    logger.info({ jobId, fileId }, "Created job for video processing");

    // Start processing job asynchronously with odometer image path if provided
    const odometerImagePath = odometerImageFile
      ? odometerImageFile.path
      : undefined;
    const vehicleIdentityOverride = vehicleIdentityOverrideFromBody(req);

    // Update status to processing — job_processor owns all progress updates
    updateJobStatus(jobId, {
      status: "processing",
    });

    logger.debug(
      { jobId },
      "Job status updated to processing, starting async processing",
    );

    // Wrap in immediate async function to catch any synchronous errors
    (async () => {
      try {
        await processVideoJob(
          jobId,
          fileId,
          videoFile.path,
          odometerImagePath,
          vehicleIdentityOverride,
        );
      } catch (error) {
        // If processVideoJob didn't update the status (shouldn't happen, but safety net)
        logger.error(
          { jobId, error },
          "Job processing failed with unhandled error",
        );
        // Ensure job status is updated even if processVideoJob failed silently
        try {
          updateJobStatus(jobId, {
            status: "failed",
            error_message:
              error instanceof Error ? error.message : String(error),
          });
        } catch (updateError) {
          logger.error(
            { jobId, updateError },
            "Failed to update job status after error",
          );
        }
      }
    })();

    // Return job ID and file info
    res.status(202).json({
      jobId: jobRecord.id,
      fileId: fileRecord.id,
      message: "Video uploaded successfully. Processing started.",
      odometerImageUploaded: !!odometerImageFile,
      vehicleIdentityEvidenceUploaded: !!vehicleIdentityOverride,
    });
  }),
);

export default router;
