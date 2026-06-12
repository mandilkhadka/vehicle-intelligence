/**
 * Job processor service
 * Handles video processing jobs asynchronously
 */

import axios, { AxiosError, AxiosResponse } from "axios";
import { v4 as uuidv4 } from "uuid";
import * as fs from "fs";
import * as path from "path";
import { z } from "zod";
import {
  updateJobStatus,
  createInspection,
  updateInspection,
} from "../models/inspection";
import { config } from "../config/env";
import { PROGRESS_SIMULATION } from "../config/constants";
import logger from "../utils/logger";

// Loose schema: ML service is trusted, but a malformed JSON body (e.g.
// "value": "NaN") should be coerced/rejected before we persist it.
const confidenceSchema = z
  .union([z.number(), z.null()])
  .optional()
  .transform((v) => {
    if (v === null || v === undefined || Number.isNaN(v as number)) return undefined;
    if (typeof v !== "number") return undefined;
    return Math.max(0, Math.min(1, v));
  });

const countSchema = z
  .union([z.number(), z.null()])
  .optional()
  .transform((v) => {
    if (typeof v !== "number" || Number.isNaN(v) || v < 0) return 0;
    return Math.floor(v);
  });

const mlResponseSchema = z
  .object({
    inspection_id: z.string().optional(),
    frames: z.array(z.string()).optional().default([]),
    vehicle_info: z
      .object({
        type: z.string().optional(),
        brand: z.string().optional(),
        model: z.string().optional(),
        year: z.union([z.string(), z.number()]).optional(),
        variant: z.string().optional(),
        confidence: confidenceSchema,
      })
      .passthrough()
      .optional()
      .default({}),
    odometer: z
      .object({
        value: z.union([z.number(), z.null()]).optional(),
        confidence: confidenceSchema,
        speedometer_image_path: z.string().nullable().optional(),
      })
      .passthrough()
      .optional()
      .default({}),
    damage: z
      .object({
        severity: z.string().optional(),
        scratches: z.object({ count: countSchema }).passthrough().optional(),
        dents: z.object({ count: countSchema }).passthrough().optional(),
        rust: z.object({ count: countSchema }).passthrough().optional(),
        cracks: z.object({ count: countSchema }).passthrough().optional(),
        paint_damage: z.object({ count: countSchema }).passthrough().optional(),
        // Sprint 1 additions — part-grounded locations + cost + rationale.
        locations: z
          .array(
            z
              .object({
                type: z.string().optional(),
                part: z.string().optional(),
                part_label: z.string().optional(),
                part_confidence: z.number().min(0).max(1).optional(),
                confidence: confidenceSchema,
                severity: z.string().optional(),
                frame: z.string().nullable().optional(),
                snapshot: z.string().nullable().optional(),
                bbox: z.array(z.number()).optional(),
                mask: z.array(z.array(z.number())).nullable().optional(),
                frame_width: z.number().optional(),
                frame_height: z.number().optional(),
                source: z.string().optional(),
                rationale: z.string().nullable().optional(),
                rationale_likely_real: z.boolean().nullable().optional(),
                estimated_cost: z
                  .object({
                    low: z.number(),
                    high: z.number(),
                    midpoint: z.number(),
                    currency: z.string(),
                  })
                  .nullable()
                  .optional(),
              })
              .passthrough(),
          )
          .optional(),
        total_estimated_repair_cost: z
          .object({
            low: z.number(),
            high: z.number(),
            midpoint: z.number(),
            currency: z.string(),
            has_unknowns: z.boolean().optional(),
            counted_locations: z.number().optional(),
            unknown_locations: z.number().optional(),
          })
          .optional(),
        rationale_available: z.boolean().optional(),
        rationale_count: z.number().optional(),
      })
      .passthrough()
      .optional()
      .default({}),
    exhaust: z
      .object({
        type: z.string().optional(),
        confidence: confidenceSchema,
        exhaust_image_path: z.string().nullable().optional(),
      })
      .passthrough()
      .optional()
      .default({}),
    report: z.unknown().optional(),
  })
  .passthrough();

type ErrorDetails = Record<string, unknown>;

function mlServiceHeaders(): Record<string, string> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (config.mlService.apiKey) {
    headers["X-Internal-API-Key"] = config.mlService.apiKey;
  }
  return headers;
}

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
    if (
      axiosError.code === "ECONNREFUSED" ||
      axiosError.code === "ETIMEDOUT" ||
      axiosError.code === "ECONNABORTED" ||
      axiosError.code === "ENOTFOUND"
    ) {
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
  odometerImagePath?: string,
  vehicleIdentityOverride?: Record<string, unknown>,
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

    logger.debug(
      { jobId, videoPath: absoluteVideoPath },
      "Video file verified",
    );

    updateJobStatus(jobId, {
      status: "processing",
      progress: 10,
    });

    // Check ML service health before processing
    const mlServiceHealthUrl = `${config.mlService.url}/health`;
    try {
      logger.debug(
        { jobId, url: mlServiceHealthUrl },
        "Checking ML service health",
      );
      await axios.get(mlServiceHealthUrl, { timeout: 10000 });
      logger.debug({ jobId }, "ML service is healthy");
    } catch (healthError) {
      logger.error(
        { jobId, error: healthError, url: mlServiceHealthUrl },
        "ML service health check failed",
      );
      throw new Error(
        "ML service is not available. Please ensure the ML service is running on " +
          `${config.mlService.url}. Check the service logs for details.`,
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
        logger.warn(
          { jobId, path: absoluteOdometerPath },
          "Odometer image not found, proceeding without it",
        );
        absoluteOdometerPath = undefined;
      } else {
        logger.debug(
          { jobId, odometerPath: absoluteOdometerPath },
          "Odometer image verified",
        );
      }
    }

    logger.info(
      {
        jobId,
        mlServiceUrl,
        videoPath: absoluteVideoPath,
        hasOdometerImage: !!absoluteOdometerPath,
        timeout: config.mlService.timeout,
      },
      "Calling ML service for video processing",
    );

    // Set up progress simulation during ML service processing
    // This helps show that processing is ongoing even if ML service takes time
    let progressInterval: NodeJS.Timeout | null = null;
    let currentProgress = PROGRESS_SIMULATION.MIN_PROGRESS;
    const progressIncrement = PROGRESS_SIMULATION.INCREMENT;
    const progressIntervalMs = PROGRESS_SIMULATION.INTERVAL_MS;

    const startProgressSimulation = () => {
      progressInterval = setInterval(() => {
        if (currentProgress < PROGRESS_SIMULATION.MAX_PROGRESS) {
          // Cap at 85% during simulation
          currentProgress += progressIncrement;
          updateJobStatus(jobId, {
            status: "processing",
            progress: currentProgress,
          });
          logger.debug(
            { jobId, progress: currentProgress },
            "Progress update during ML processing",
          );
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
      logger.debug(
        { jobId },
        "ML service initializing models (this may take 30-60 seconds)...",
      );

      // Retry loop for ML service requests
      while (retryAttempt <= RETRY_CONFIG.maxRetries) {
        try {
          if (retryAttempt > 0) {
            const delay = calculateBackoffDelay(retryAttempt - 1);
            logger.info(
              {
                jobId,
                attempt: retryAttempt,
                maxRetries: RETRY_CONFIG.maxRetries,
                delayMs: delay,
              },
              `Retrying ML service request after ${delay}ms delay`,
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
              vehicle_identity_override: vehicleIdentityOverride,
            },
            {
              timeout: config.mlService.timeout,
              headers: mlServiceHeaders(),
              // Add request timeout handler
              validateStatus: (status) => status < 500, // Don't throw on 4xx errors
              maxContentLength: 50 * 1024 * 1024, // 50MB
              maxBodyLength: 50 * 1024 * 1024, // 50MB
            },
          );

          // Check for error responses (4xx errors - not retryable)
          if (response.status >= 400) {
            const rawError =
              response.data?.detail ||
              response.data?.error?.message ||
              response.data?.error ||
              `ML service returned error: ${response.status}`;
            const errorMessage =
              typeof rawError === "string"
                ? rawError
                : JSON.stringify(rawError);
            logger.error(
              { jobId, status: response.status, error: errorMessage },
              "ML service returned error",
            );
            throw new Error(errorMessage);
          }

          // Success - break out of retry loop
          break;
        } catch (attemptError) {
          // Check if error is retryable and we have retries left
          if (
            isRetryableError(attemptError) &&
            retryAttempt < RETRY_CONFIG.maxRetries
          ) {
            retryAttempt++;
            logger.warn(
              {
                jobId,
                attempt: retryAttempt,
                maxRetries: RETRY_CONFIG.maxRetries,
                error: attemptError,
              },
              "ML service request failed, will retry",
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
        "ML service request completed successfully",
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
        "ML service request failed after all retry attempts",
      );
      throw requestError;
    }

    logger.info({ jobId, inspectionId }, "ML service processing completed");

    // Update progress to show we're processing results
    updateJobStatus(jobId, {
      status: "processing",
      progress: 90,
    });

    // Validate ML response shape before persisting. We don't reject on extra
    // fields — passthrough() preserves them — but we coerce confidences into
    // [0, 1] and counts into non-negative integers so the DB never stores
    // out-of-range values.
    const parsed = mlResponseSchema.safeParse(response.data);
    if (!parsed.success) {
      logger.error(
        { jobId, issues: parsed.error.issues },
        "ML service returned a malformed response body",
      );
      throw new Error("ML service returned an unexpected response shape");
    }
    const results = parsed.data;

    const yearValue = results.vehicle_info?.year;
    updateInspection(inspectionId, {
      vehicle_type: results.vehicle_info?.type,
      vehicle_brand: results.vehicle_info?.brand,
      vehicle_model: results.vehicle_info?.model,
      vehicle_year: yearValue === undefined ? undefined : String(yearValue),
      vehicle_variant: results.vehicle_info?.variant,
      vehicle_confidence: results.vehicle_info?.confidence,
      vehicle_info: JSON.stringify(results.vehicle_info || {}),
      odometer_value: results.odometer?.value ?? undefined,
      odometer_confidence: results.odometer?.confidence,
      speedometer_image_path: results.odometer?.speedometer_image_path ?? undefined,
      odometer_info: JSON.stringify(results.odometer || {}),
      damage_summary: JSON.stringify(results.damage || {}),
      scratches_detected: results.damage?.scratches?.count || 0,
      dents_detected: results.damage?.dents?.count || 0,
      rust_detected: results.damage?.rust?.count || 0,
      cracks_detected: results.damage?.cracks?.count || 0,
      paint_damage_detected: results.damage?.paint_damage?.count || 0,
      damage_severity: results.damage?.severity,
      exhaust_type: results.exhaust?.type,
      exhaust_confidence: results.exhaust?.confidence,
      exhaust_image_path: results.exhaust?.exhaust_image_path ?? undefined,
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
      "Video processing job completed successfully",
    );
  } catch (error) {
    const duration = Date.now() - startTime;

    // Extract meaningful error message
    let errorMessage = "Unknown error during processing";
    let errorDetails: ErrorDetails = {};

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
        const data = axiosError.response.data;
        if (typeof data === "string") {
          errorMessage = data;
        } else if (isRecord(data)) {
          if (typeof data.detail === "string") {
            errorMessage = data.detail;
          } else if (typeof data.message === "string") {
            errorMessage = data.message;
          } else if (typeof data.error === "string") {
            errorMessage = data.error;
          }
        }
      }

      // Handle specific error codes
      if (axiosError.code === "ECONNREFUSED") {
        errorMessage =
          "ML service is not available. Please ensure the ML service is running.";
      } else if (
        axiosError.code === "ETIMEDOUT" ||
        axiosError.code === "ECONNABORTED"
      ) {
        errorMessage =
          "Request to ML service timed out. The video may be too large or the service is overloaded.";
      } else if (axiosError.code === "ENOTFOUND") {
        errorMessage =
          "Cannot reach ML service. Please check the service URL configuration.";
      } else if (axiosError.response?.status === 400) {
        errorMessage =
          errorMessage ||
          "Invalid request to ML service. Please check the video file.";
      } else if (axiosError.response?.status === 500) {
        errorMessage =
          errorMessage ||
          "ML service encountered an internal error. Please try again later.";
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
      "Video processing job failed",
    );

    updateJobStatus(jobId, {
      status: "failed",
      error_message: errorMessage,
    });

    // Clean up the uploaded video on permanent failure so we don't accumulate
    // multi-hundred-MB files for jobs that will never succeed. Frames and
    // snapshots are kept for debugging.
    try {
      const absoluteVideoPath = path.isAbsolute(videoPath)
        ? videoPath
        : path.join(process.cwd(), videoPath);
      if (fs.existsSync(absoluteVideoPath)) {
        fs.unlinkSync(absoluteVideoPath);
        logger.info({ jobId, absoluteVideoPath }, "Removed video for failed job");
      }
    } catch (cleanupError) {
      logger.warn({ jobId, cleanupError }, "Failed to remove video after job failure");
    }

    throw error;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
