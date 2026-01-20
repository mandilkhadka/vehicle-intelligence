/**
 * Job processor service
 * Handles video processing jobs asynchronously
 */

import axios, { AxiosError } from "axios";
import { v4 as uuidv4 } from "uuid";
import {
  updateJobStatus,
  createInspection,
  updateInspection,
} from "../models/inspection";
import { config } from "../config/env";
import logger from "../utils/logger";

/**
 * Process a video job
 * This function orchestrates the entire video processing pipeline
 */
export async function processVideoJob(
  jobId: string,
  fileId: string,
  videoPath: string,
  odometerImagePath?: string
): Promise<void> {
  const startTime = Date.now();
  
  try {
    logger.info({ jobId, fileId, videoPath }, "Starting video processing job");

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

    logger.debug({ jobId, inspectionId }, "Created inspection record");

    // Call ML service to process video
    updateJobStatus(jobId, {
      status: "processing",
      progress: 20,
    });

    const mlServiceUrl = `${config.mlService.url}/api/process`;
    logger.debug({ jobId, mlServiceUrl }, "Calling ML service");

    const response = await axios.post(
      mlServiceUrl,
      {
        video_path: videoPath,
        inspection_id: inspectionId,
        odometer_image_path: odometerImagePath,
      },
      {
        timeout: config.mlService.timeout,
        headers: {
          "Content-Type": "application/json",
        },
      }
    );

    logger.info({ jobId, inspectionId }, "ML service processing completed");

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
      exhaust_image_path: results.exhaust?.exhaust_image_path,
      inspection_report: JSON.stringify(results.report || {}),
      extracted_frames: JSON.stringify(results.frames || []),
    });

    // Update job status to completed
    updateJobStatus(jobId, {
      status: "completed",
      progress: 100,
      inspection_id: inspectionId,
    });

    const duration = Date.now() - startTime;
    logger.info(
      { jobId, inspectionId, duration },
      "Video processing job completed successfully"
    );
  } catch (error) {
    const duration = Date.now() - startTime;
    const axiosError = error as AxiosError;

    logger.error(
      {
        jobId,
        error: axiosError.message,
        code: axiosError.code,
        response: axiosError.response?.data,
        duration,
      },
      "Video processing job failed"
    );

    // Extract meaningful error message
    let errorMessage = "Unknown error during processing";
    
    if (axiosError.response?.data) {
      const data = axiosError.response.data as any;
      errorMessage = data.detail || data.message || errorMessage;
    } else if (axiosError.message) {
      errorMessage = axiosError.message;
    } else if (axiosError.code === "ECONNREFUSED") {
      errorMessage = "ML service is not available. Please ensure the ML service is running.";
    } else if (axiosError.code === "ETIMEDOUT" || axiosError.code === "ECONNABORTED") {
      errorMessage = "Request to ML service timed out. The video may be too large or the service is overloaded.";
    }

    updateJobStatus(jobId, {
      status: "failed",
      error_message: errorMessage,
    });

    throw error;
  }
}
