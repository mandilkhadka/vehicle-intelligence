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
  getUploadPath,
} from "../utils/fileUtils";
import { processVideoJob } from "../services/job_processor";

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

const upload = multer({
  storage,
  fileFilter,
  limits: {
    fileSize: 500 * 1024 * 1024, // 500MB limit
  },
});

/**
 * POST /api/upload
 * Upload a video file and create a processing job
 */
router.post("/", upload.single("video"), async (req: Request, res: Response) => {
  try {
    // Check if file was uploaded
    if (!req.file) {
      return res.status(400).json({ error: "No file uploaded" });
    }

    // Generate IDs
    const fileId = uuidv4();
    const jobId = uuidv4();

    // Create file record in database
    const fileRecord = createFile({
      id: fileId,
      filename: req.file.filename,
      original_filename: req.file.originalname,
      file_path: req.file.path,
      file_size: req.file.size,
      mime_type: req.file.mimetype,
    });

    // Create job record
    const jobRecord = createJob({
      id: jobId,
      file_id: fileId,
      status: "pending",
    });

    // Start processing job asynchronously
    processVideoJob(jobId, fileId, req.file.path).catch((error) => {
      console.error(`Job ${jobId} failed:`, error);
      updateJobStatus(jobId, {
        status: "failed",
        error_message: error.message || "Unknown error",
      });
    });

    // Return job ID and file info
    res.json({
      jobId: jobRecord.id,
      fileId: fileRecord.id,
      message: "Video uploaded successfully. Processing started.",
    });
  } catch (error: any) {
    console.error("Upload error:", error);
    res.status(500).json({
      error: "Failed to upload video",
      message: error.message,
    });
  }
});

export default router;
