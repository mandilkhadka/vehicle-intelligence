/**
 * API client for communicating with the backend
 * Handles all HTTP requests to the backend API
 */

import axios from "axios";

// Base URL for the backend API
const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:3001/api";

// Base URL for static asset references (frame images, snapshots, etc.).
// We rewrite /uploads/* through Next so Next/Image can optimize without
// being blocked by the private-IP guard. An override is still supported
// for deployments that serve assets from a different origin.
export const BACKEND_BASE_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "";

// Create axios instance with default config
const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    "Content-Type": "application/json",
  },
});

/**
 * Upload a video file to the backend
 * @param file - The video file to upload
 * @param odometerImage - Optional odometer image file
 * @param onProgress - Optional callback for upload progress
 * @returns Promise with job ID and file info
 */
export async function uploadVideo(
  file: File,
  odometerImage?: File | null,
  onProgress?: (progress: number) => void,
): Promise<{ jobId: string; fileId: string }> {
  const formData = new FormData();
  formData.append("video", file);
  if (odometerImage) {
    formData.append("odometer_image", odometerImage);
  }

  const response = await apiClient.post("/upload", formData, {
    headers: {
      "Content-Type": "multipart/form-data",
    },
    onUploadProgress: (progressEvent) => {
      if (onProgress && progressEvent.total) {
        const percentCompleted = Math.round(
          (progressEvent.loaded * 100) / progressEvent.total,
        );
        onProgress(percentCompleted);
      }
    },
  });

  return response.data;
}

/**
 * Get the status of a processing job
 * @param jobId - The job ID to check
 * @returns Promise with job status
 */
export async function getJobStatus(jobId: string): Promise<{
  id: string;
  status: "pending" | "processing" | "completed" | "failed";
  progress?: number;
  inspectionId?: string;
  inspection_id?: string;
  error?: string;
  error_message?: string;
}> {
  const response = await apiClient.get(`/jobs/${jobId}`);
  return response.data;
}

/**
 * Inspection record returned by the backend API
 */
export interface InspectionRecord {
  id: string;
  job_id: string;
  file_id: string;
  vehicle_type?: string;
  vehicle_brand?: string;
  vehicle_model?: string;
  vehicle_confidence?: number;
  odometer_value?: number;
  odometer_confidence?: number;
  speedometer_image_path?: string;
  damage_summary?: string | Record<string, unknown>;
  scratches_detected?: number;
  dents_detected?: number;
  rust_detected?: number;
  damage_severity?: string;
  exhaust_type?: string;
  exhaust_confidence?: number;
  exhaust_image_path?: string;
  inspection_report?: string | Record<string, unknown>;
  extracted_frames?: string | string[];
  created_at: string;
  updated_at: string;
}

/**
 * Get inspection results by ID
 * @param inspectionId - The inspection ID
 * @returns Promise with inspection data
 */
export async function getInspection(
  inspectionId: string,
): Promise<InspectionRecord> {
  const response = await apiClient.get(`/inspections/${inspectionId}`);
  return response.data;
}

/**
 * Get all inspections
 * @returns Promise with list of inspections
 */
export async function getInspections(): Promise<InspectionRecord[]> {
  const response = await apiClient.get("/inspections");
  const result = response.data;
  return Array.isArray(result) ? result : result.data || [];
}

/**
 * Metrics response from backend
 */
export interface MetricsResponse {
  summary: {
    totalInspections: number;
    uniqueVehicles: number;
    totalIssues: number;
    avgProcessingTime: number;
  };
  dailyTrend: Array<{
    date: string;
    issues: number;
  }>;
  damageBreakdown: {
    scratches: number;
    dents: number;
    rust: number;
  };
  vehicleBreakdown: Array<{
    brand: string;
    count: number;
  }>;
}

/**
 * Get dashboard metrics for a date range
 * @param startDate - Start date (YYYY-MM-DD)
 * @param endDate - End date (YYYY-MM-DD)
 * @returns Promise with metrics data
 */
export async function getMetrics(
  startDate: string,
  endDate: string,
): Promise<MetricsResponse> {
  const response = await apiClient.get("/metrics", {
    params: { startDate, endDate },
  });
  return response.data;
}

/**
 * Get inspections filtered by date range
 * @param startDate - Start date (YYYY-MM-DD)
 * @param endDate - End date (YYYY-MM-DD)
 * @param limit - Optional limit for results
 * @returns Promise with list of inspections
 */
export async function getInspectionsByDateRange(
  startDate: string,
  endDate: string,
  limit?: number,
): Promise<InspectionRecord[]> {
  const response = await apiClient.get("/inspections", {
    params: { startDate, endDate, limit },
  });
  const result = response.data;
  return Array.isArray(result) ? result : result.data || [];
}

export default apiClient;
