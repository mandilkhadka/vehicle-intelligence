/**
 * Job processor service
 * Handles video processing jobs asynchronously
 */

import axios from "axios";
import { v4 as uuidv4 } from "uuid";
import {
  updateJobStatus,
  createInspection,
  updateInspection,
} from "../models/inspection";
import * as path from "path";

// ML Service URL - in production this would be an environment variable
const ML_SERVICE_URL =
  process.env.ML_SERVICE_URL || "http://localhost:8000";

/**
 * Process a video job
 * This function orchestrates the entire video processing pipeline
 */
export async function processVideoJob(
  jobId: string,
  fileId: string,
  videoPath: string
): Promise<void> {
  try {
    // Update job status to processing
    updateJobStatus(jobId, {
      status: "processing",
      progress: 10,
    });

    // Create inspection record
    const inspectionId = uuidv4();
    createInspection({
      id: inspectionId,
      job_id: jobId,
      file_id: fileId,
    });

    // Call ML service to process video
    updateJobStatus(jobId, {
      status: "processing",
      progress: 20,
    });

    // Convert absolute path to relative path for ML service
    const path = require("path");
    const relativeVideoPath = path.relative(
      path.join(process.cwd(), ".."),
      videoPath
    );

    const response = await axios.post(`${ML_SERVICE_URL}/api/process`, {
      video_path: videoPath, // Use absolute path for ML service
      inspection_id: inspectionId,
    });

    // Update inspection with results
    const results = response.data;

    updateInspection(inspectionId, {
      vehicle_type: results.vehicle_info?.type,
      vehicle_brand: results.vehicle_info?.brand,
      vehicle_model: results.vehicle_info?.model,
      vehicle_confidence: results.vehicle_info?.confidence,
      odometer_value: results.odometer?.value,
      odometer_confidence: results.odometer?.confidence,
      speedometer_image_path: results.odometer?.speedometer_image_path,
      damage_summary: JSON.stringify(results.damage || {}),
      scratches_detected: results.damage?.scratches?.count || 0,
      dents_detected: results.damage?.dents?.count || 0,
      rust_detected: results.damage?.rust?.count || 0,
      damage_severity: results.damage?.severity,
      exhaust_type: results.exhaust?.type,
      exhaust_confidence: results.exhaust?.confidence,
      inspection_report: JSON.stringify(results.report || {}),
      extracted_frames: JSON.stringify(results.frames || []),
    });

    // Update job status to completed
    updateJobStatus(jobId, {
      status: "completed",
      progress: 100,
      inspection_id: inspectionId,
    });
  } catch (error: any) {
    console.error(`Job ${jobId} processing error:`, error);
    updateJobStatus(jobId, {
      status: "failed",
      error_message: error.message || "Unknown error during processing",
    });
    throw error;
  }
}
