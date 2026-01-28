/**
 * Job processor service
 * Handles video processing jobs asynchronously
 */

import axios, { AxiosError, AxiosResponse } from "axios";
import { v4 as uuidv4 } from "uuid";
import * as fs from "fs";
import * as path from "path";
import {
  updateJobStatus,
  createInspection,
  updateInspection,
} from "../models/inspection";
import { config } from "../config/env";
import logger from "../utils/logger";

// Retry configuration
const RETRY_CONFIG = {
  maxRetries: 3,
  baseDelayMs: 1000, // 1 second base delay
  maxDelayMs: 30000, // 30 seconds max delay
};

/**
 * Calculate exponential backoff delay
 * @param attempt - Current retry attempt (0-based)
 * @returns Delay in milliseconds
 */
function calculateBackoffDelay(attempt: number): number {
  const delay = RETRY_CONFIG.baseDelayMs * Math.pow(2, attempt);
  return Math.min(delay, RETRY_CONFIG.maxDelayMs);
}

/**
 * Determine if an error is retryable
 * @param error - The error to check
 * @returns true if the error is retryable
 */
function isRetryableError(error: unknown): boolean {
  if (axios.isAxiosError(error)) {
    const axiosError = error as AxiosError;
    // Retry on connection errors
    if (axiosError.code === "ECONNREFUSED" ||
        axiosError.code === "ETIMEDOUT" ||
        axiosError.code === "ECONNABORTED" ||
        axiosError.code === "ENOTFOUND") {
      return true;
    }
    // Retry on 5xx server errors
    if (axiosError.response?.status && axiosError.response.status >= 500) {
      return true;
    }
  }
  return false;
}

/**
 * Sleep for a specified duration
 * @param ms - Duration in milliseconds
 */
function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

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
      progress: 5,
    });

    // Create inspection record
    const inspectionId = uuidv4();
    createInspection({
      id: inspectionId,
      job_id: jobId,
      file_id: fileId,
    });

    logger.debug({ jobId, inspectionId }, "Created inspection record");

    // Verify video file exists
    const absoluteVideoPath = path.isAbsolute(videoPath) 
      ? videoPath 
      : path.join(process.cwd(), videoPath);
    
    if (!fs.existsSync(absoluteVideoPath)) {
      throw new Error(`Video file not found: ${absoluteVideoPath}`);
    }
    
    logger.debug({ jobId, videoPath: absoluteVideoPath }, "Video file verified");
    
    updateJobStatus(jobId, {
      status: "processing",
      progress: 10,
    });

    // Check ML service health before processing
    const mlServiceHealthUrl = `${config.mlService.url}/health`;
    try {
      logger.debug({ jobId, url: mlServiceHealthUrl }, "Checking ML service health");
      await axios.get(mlServiceHealthUrl, { timeout: 10000 });
      logger.debug({ jobId }, "ML service is healthy");
    } catch (healthError) {
      logger.error(
        { jobId, error: healthError, url: mlServiceHealthUrl },
        "ML service health check failed"
      );
      throw new Error(
        "ML service is not available. Please ensure the ML service is running on " +
        `${config.mlService.url}. Check the service logs for details.`
      );
    }
    
    updateJobStatus(jobId, {
      status: "processing",
      progress: 15,
    });

    // Call ML service to process video
    updateJobStatus(jobId, {
      status: "processing",
      progress: 20,
    });

    const mlServiceUrl = `${config.mlService.url}/api/process`;
    
    // Prepare odometer image path if provided
    let absoluteOdometerPath: string | undefined;
    if (odometerImagePath) {
      absoluteOdometerPath = path.isAbsolute(odometerImagePath)
        ? odometerImagePath
        : path.join(process.cwd(), odometerImagePath);
      
      if (!fs.existsSync(absoluteOdometerPath)) {
        logger.warn({ jobId, path: absoluteOdometerPath }, "Odometer image not found, proceeding without it");
        absoluteOdometerPath = undefined;
      } else {
        logger.debug({ jobId, odometerPath: absoluteOdometerPath }, "Odometer image verified");
      }
    }

    logger.info(
      { 
        jobId, 
        mlServiceUrl, 
        videoPath: absoluteVideoPath,
        hasOdometerImage: !!absoluteOdometerPath,
        timeout: config.mlService.timeout 
      }, 
      "Calling ML service for video processing"
    );

    // Set up progress simulation during ML service processing
    // This helps show that processing is ongoing even if ML service takes time
    let progressInterval: NodeJS.Timeout | null = null;
    let currentProgress = 20;
    const progressIncrement = 5; // Increment by 5% every 10 seconds
    const progressIntervalMs = 10000; // Update every 10 seconds
    
    const startProgressSimulation = () => {
      progressInterval = setInterval(() => {
        if (currentProgress < 85) { // Cap at 85% during simulation
          currentProgress += progressIncrement;
          updateJobStatus(jobId, {
            status: "processing",
            progress: currentProgress,
          });
          logger.debug({ jobId, progress: currentProgress }, "Progress update during ML processing");
        }
      }, progressIntervalMs);
    };

    const stopProgressSimulation = () => {
      if (progressInterval) {
        clearInterval(progressInterval);
        progressInterval = null;
      }
    };

    const requestStartTime = Date.now();
    let response!: AxiosResponse;

    // ML service call with retry logic
    let retryAttempt = 0;

    try {
      // Start progress simulation
      startProgressSimulation();

      // Update progress to indicate ML service is initializing
      updateJobStatus(jobId, {
        status: "processing",
        progress: 25,
      });
      logger.debug({ jobId }, "ML service initializing models (this may take 30-60 seconds)...");

      // Retry loop for ML service requests
      while (retryAttempt <= RETRY_CONFIG.maxRetries) {
        try {
          if (retryAttempt > 0) {
            const delay = calculateBackoffDelay(retryAttempt - 1);
            logger.info(
              { jobId, attempt: retryAttempt, maxRetries: RETRY_CONFIG.maxRetries, delayMs: delay },
              `Retrying ML service request after ${delay}ms delay`
            );
            await sleep(delay);

            // Update job status to indicate retry
            updateJobStatus(jobId, {
              status: "processing",
              progress: 20 + retryAttempt * 2,
            });
          }

          response = await axios.post(
            mlServiceUrl,
            {
              video_path: absoluteVideoPath,
              inspection_id: inspectionId,
              odometer_image_path: absoluteOdometerPath,
            },
            {
              timeout: config.mlService.timeout,
              headers: {
                "Content-Type": "application/json",
              },
              // Add request timeout handler
              validateStatus: (status) => status < 500, // Don't throw on 4xx errors
              // Increase max content length
              maxContentLength: Infinity,
              maxBodyLength: Infinity,
            }
          );

          // Check for error responses (4xx errors - not retryable)
          if (response.status >= 400) {
            const errorMessage = response.data?.detail || response.data?.error || `ML service returned error: ${response.status}`;
            logger.error({ jobId, status: response.status, error: errorMessage }, "ML service returned error");
            throw new Error(errorMessage);
          }

          // Success - break out of retry loop
          break;
        } catch (attemptError) {

          // Check if error is retryable and we have retries left
          if (isRetryableError(attemptError) && retryAttempt < RETRY_CONFIG.maxRetries) {
            retryAttempt++;
            logger.warn(
              { jobId, attempt: retryAttempt, maxRetries: RETRY_CONFIG.maxRetries, error: attemptError },
              "ML service request failed, will retry"
            );
            continue;
          }

          // Non-retryable error or out of retries
          throw attemptError;
        }
      }

      // Stop progress simulation
      stopProgressSimulation();

      const requestDuration = Date.now() - requestStartTime;
      logger.info(
        { jobId, duration: requestDuration, retryAttempts: retryAttempt },
        "ML service request completed successfully"
      );
    } catch (requestError) {
      // Stop progress simulation on error
      stopProgressSimulation();

      const requestDuration = Date.now() - requestStartTime;
      logger.error(
        {
          jobId,
          error: requestError,
          duration: requestDuration,
          url: mlServiceUrl,
          totalAttempts: retryAttempt + 1,
        },
        "ML service request failed after all retry attempts"
      );
      throw requestError;
    }

    logger.info({ jobId, inspectionId }, "ML service processing completed");

    // Update progress to show we're processing results
    updateJobStatus(jobId, {
      status: "processing",
      progress: 90,
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
    
    // Extract meaningful error message
    let errorMessage = "Unknown error during processing";
    let errorDetails: any = {};

    // Check if it's an AxiosError
    if (axios.isAxiosError(error)) {
      const axiosError = error as AxiosError;
      
      errorDetails = {
        message: axiosError.message,
        code: axiosError.code,
        status: axiosError.response?.status,
        responseData: axiosError.response?.data,
        url: axiosError.config?.url,
      };

      // Extract error message from response data
      if (axiosError.response?.data) {
        const data = axiosError.response.data as any;
        if (typeof data === "string") {
          errorMessage = data;
        } else if (data.detail) {
          errorMessage = data.detail;
        } else if (data.message) {
          errorMessage = data.message;
        } else if (data.error) {
          errorMessage = data.error;
        }
      }
      
      // Handle specific error codes
      if (axiosError.code === "ECONNREFUSED") {
        errorMessage = "ML service is not available. Please ensure the ML service is running.";
      } else if (axiosError.code === "ETIMEDOUT" || axiosError.code === "ECONNABORTED") {
        errorMessage = "Request to ML service timed out. The video may be too large or the service is overloaded.";
      } else if (axiosError.code === "ENOTFOUND") {
        errorMessage = "Cannot reach ML service. Please check the service URL configuration.";
      } else if (axiosError.response?.status === 400) {
        errorMessage = errorMessage || "Invalid request to ML service. Please check the video file.";
      } else if (axiosError.response?.status === 500) {
        errorMessage = errorMessage || "ML service encountered an internal error. Please try again later.";
      } else if (axiosError.message && !errorMessage.includes("Unknown")) {
        errorMessage = axiosError.message;
      }
    } else if (error instanceof Error) {
      // Handle regular Error objects
      errorDetails = {
        message: error.message,
        name: error.name,
        stack: error.stack,
      };
      errorMessage = error.message || errorMessage;
    } else {
      // Handle unknown error types
      errorDetails = {
        error: String(error),
        type: typeof error,
      };
      errorMessage = String(error) || errorMessage;
    }

    logger.error(
      {
        jobId,
        ...errorDetails,
        duration,
      },
      "Video processing job failed"
    );

    updateJobStatus(jobId, {
      status: "failed",
      error_message: errorMessage,
    });

    throw error;
  }
}
