/**
 * Upload route handler
 * Handles video file uploads
 */

import { Router, Request, Response } from "express";
import multer from "multer";
import { v4 as uuidv4 } from "uuid";
import * as path from "path";
import {
  createFile,
  createJob,
  updateJobStatus,
} from "../models/inspection";
import {
  ensureDirectoryExists,
  generateUniqueFilename,
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

// Configure multer for file uploads
const storage = multer.diskStorage({
  destination: (req, file, cb) => {
    // Set upload destination
    const uploadPath = getUploadPath("videos");
    ensureDirectoryExists(uploadPath);
    cb(null, uploadPath);
  },
  filename: (req, file, cb) => {
    // Generate unique filename
    const uniqueFilename = generateUniqueFilename(file.originalname);
    cb(null, uniqueFilename);
  },
});

// File filter to only accept video files
const fileFilter = (
  req: Request,
  file: Express.Multer.File,
  cb: multer.FileFilterCallback
) => {
  if (isValidVideoFormat(file.originalname)) {
    cb(null, true);
  } else {
    cb(new Error("Invalid file format. Only video files are allowed."));
  }
};

// Configure multer for odometer images
const odometerStorage = multer.diskStorage({
  destination: (req, file, cb) => {
    const uploadPath = getUploadPath("odometer_images");
    ensureDirectoryExists(uploadPath);
    cb(null, uploadPath);
  },
  filename: (req, file, cb) => {
    const uniqueFilename = generateUniqueFilename(file.originalname);
    cb(null, uniqueFilename);
  },
});

// File filter for images
const imageFileFilter = (
  req: Request,
  file: Express.Multer.File,
  cb: multer.FileFilterCallback
) => {
  if (isValidImageFormat(file.originalname)) {
    cb(null, true);
  } else {
    cb(new Error("Invalid file format. Only image files are allowed."));
  }
};

const upload = multer({
  storage,
  fileFilter,
  limits: {
    fileSize: config.upload.maxSize,
  },
});

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
  cb: multer.FileFilterCallback
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

/**
 * POST /api/upload
 * Upload a video file and optional odometer image, then create a processing job
 */
router.post(
  "/",
  (req: Request, res: Response, next: any) => {
    uploadWithOdometer(req, res, (err: any) => {
      if (err) {
        // Handle multer errors
        if (err instanceof multer.MulterError) {
          if (err.code === "LIMIT_FILE_SIZE") {
            return next(
              new CustomError(
                `File size exceeds maximum allowed size of ${config.upload.maxSize / 1024 / 1024}MB`,
                400,
                "FILE_TOO_LARGE"
              )
            );
          }
          if (err.code === "LIMIT_UNEXPECTED_FILE") {
            return next(
              new CustomError("Invalid file field", 400, "INVALID_FILE_FIELD")
            );
          }
          return next(
            new CustomError(`Upload error: ${err.message}`, 400, "UPLOAD_ERROR")
          );
        }
        // Handle file filter errors
        return next(
          new CustomError(
            err.message || "Invalid file format",
            400,
            "FILE_VALIDATION_ERROR"
          )
        );
      }
      next();
    });
  },
  asyncHandler(async (req: Request, res: Response) => {
    const files = req.files as { [fieldname: string]: Express.Multer.File[] };

    // Check if video was uploaded
    if (!files || !files.video || !files.video[0]) {
      throw new CustomError("No video file uploaded", 400, "NO_VIDEO_FILE");
    }

    const videoFile = files.video[0];
    const odometerImageFile = files.odometer_image?.[0];

    logger.info(
      {
        videoFilename: videoFile.originalname,
        videoSize: videoFile.size,
        hasOdometerImage: !!odometerImageFile,
      },
      "Processing video upload"
    );

    // Validate odometer image if provided
    if (odometerImageFile && !isValidImageFormat(odometerImageFile.originalname)) {
      throw new CustomError(
        "Invalid odometer image format. Supported: JPG, PNG, HEIC, WEBP",
        400,
        "INVALID_IMAGE_FORMAT"
      );
    }

    // Validate video MIME type
    if (!config.upload.allowedVideoTypes.includes(videoFile.mimetype)) {
      throw new CustomError(
        `Invalid video format. Allowed types: ${config.upload.allowedVideoTypes.join(", ")}`,
        400,
        "INVALID_VIDEO_FORMAT"
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
    const odometerImagePath = odometerImageFile ? odometerImageFile.path : undefined;
    processVideoJob(jobId, fileId, videoFile.path, odometerImagePath).catch((error) => {
      logger.error({ jobId, error }, "Job processing failed");
      // Error handling is already done in processVideoJob
    });

    // Return job ID and file info
    res.status(202).json({
      jobId: jobRecord.id,
      fileId: fileRecord.id,
      message: "Video uploaded successfully. Processing started.",
      odometerImageUploaded: !!odometerImageFile,
    });
  })
);

export default router;
