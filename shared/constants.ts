/**
 * Shared constants used across frontend and backend
 * Single source of truth for configuration values
 */

/**
 * Progress tracking constants
 * THRESHOLDS match frontend expectations (JobStatus.tsx)
 * Backend simulation must emit these values at appropriate stages
 */
export const PROGRESS = {
  STAGES: {
    UPLOADING: 'uploading',
    PROCESSING: 'processing',
    ANALYZING: 'analyzing',
    COMPLETING: 'completing',
    COMPLETE: 'complete',
    FAILED: 'failed',
  },
  THRESHOLDS: {
    UPLOAD_COMPLETE: 20,
    FRAME_EXTRACTION: 40,
    VEHICLE_IDENTIFIED: 55,
    ODOMETER_READ: 70,
    DAMAGE_DETECTED: 85,
    REPORT_GENERATED: 95,
    COMPLETE: 100,
  },
  SIMULATION: {
    INCREMENT: 5,
    INTERVAL_MS: 10000,
    MIN_PROGRESS: 20,
    MAX_PROGRESS: 85,
  },
} as const;

/**
 * File upload limits
 */
export const FILE_LIMITS = {
  VIDEO_MAX_SIZE_MB: 500,
  VIDEO_MAX_SIZE_BYTES: 500 * 1024 * 1024,
  IMAGE_MAX_SIZE_MB: 10,
  IMAGE_MAX_SIZE_BYTES: 10 * 1024 * 1024,
  ALLOWED_VIDEO_TYPES: [
    'video/mp4',
    'video/quicktime',
    'video/x-msvideo',
    'video/webm',
  ],
  ALLOWED_IMAGE_TYPES: [
    'image/jpeg',
    'image/png',
    'image/webp',
  ],
  ALLOWED_VIDEO_EXTENSIONS: ['.mp4', '.mov', '.avi', '.webm'],
  ALLOWED_IMAGE_EXTENSIONS: ['.jpg', '.jpeg', '.png', '.webp'],
} as const;

/**
 * API error codes for consistent error responses
 */
export const API_CODES = {
  VALIDATION_ERROR: 'VALIDATION_ERROR',
  NOT_FOUND: 'NOT_FOUND',
  PROCESSING_ERROR: 'PROCESSING_ERROR',
  ML_SERVICE_ERROR: 'ML_SERVICE_ERROR',
  UPLOAD_ERROR: 'UPLOAD_ERROR',
  INTERNAL_ERROR: 'INTERNAL_ERROR',
  UNAUTHORIZED: 'UNAUTHORIZED',
  RATE_LIMITED: 'RATE_LIMITED',
} as const;

/**
 * Type exports for use in TypeScript
 */
export type ProgressStage = typeof PROGRESS.STAGES[keyof typeof PROGRESS.STAGES];
export type ApiErrorCode = typeof API_CODES[keyof typeof API_CODES];
