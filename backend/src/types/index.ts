/**
 * Backend-specific TypeScript types
 * For shared types across frontend and backend, see shared/types.ts
 */

/**
 * Individual damage item from ML service
 */
export interface DamageItem {
  location: string;
  severity: string;
  confidence: number;
  image_path?: string;
  bbox?: [number, number, number, number];
}

/**
 * ML Service response structure
 * Used when receiving results from the ML service
 */
export interface MLServiceResponse {
  vehicle_info: {
    type: string;
    brand: string;
    model: string;
    color: string;
    year?: string;
    confidence?: number;
  } | null;
  odometer_reading?: string | null;
  odometer?: {
    value: number | null;
    confidence: number;
    speedometer_image_path?: string | null;
  } | null;
  damage_summary?: {
    scratches: DamageItem[];
    dents: DamageItem[];
    rust: DamageItem[];
  } | null;
  damage?: {
    scratches: { count: number; detected: boolean };
    dents: { count: number; detected: boolean };
    rust: { count: number; detected: boolean };
    severity: string;
    locations?: DamageItem[];
  } | null;
  exhaust_info?: {
    type: string;
    confidence: number;
    exhaust_image_path?: string;
  } | null;
  exhaust?: {
    type: string;
    confidence: number;
    exhaust_image_path?: string;
  } | null;
  extracted_frames?: string[];
  frames?: string[];
  inspection_report?: string | null;
  report?: {
    summary: string;
    recommendations: string[];
  } | null;
}

/**
 * Error details for structured error handling
 */
export interface ErrorDetails {
  message: string;
  code?: string;
  status?: number;
  responseData?: unknown;
  url?: string;
  name?: string;
  type?: string;
}

/**
 * ML Service error response structure
 */
export interface MLServiceErrorResponse {
  detail?: string;
  message?: string;
  error?: string;
}

/**
 * Retry configuration
 */
export interface RetryConfig {
  maxRetries: number;
  baseDelayMs: number;
  maxDelayMs: number;
}

/**
 * Progress configuration
 */
export interface ProgressConfig {
  increment: number;
  intervalMs: number;
  maxProgress: number;
}

/**
 * Database value types for inspection updates
 */
export type InspectionValue = string | number | null | undefined;
