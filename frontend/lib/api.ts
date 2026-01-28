/**
 * API client for communicating with the backend
 * Handles all HTTP requests to the backend API
 */

import axios from "axios";

// Base URL for the backend API
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:3001/api";

// Base URL for backend server (for static file serving)
export const BACKEND_BASE_URL = process.env.NEXT_PUBLIC_BACKEND_URL || 
  API_BASE_URL.replace("/api", "") || "http://localhost:3001";

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
  onProgress?: (progress: number) => void
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
          (progressEvent.loaded * 100) / progressEvent.total
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
 * Get inspection results by ID
 * @param inspectionId - The inspection ID
 * @returns Promise with inspection data
 */
export async function getInspection(inspectionId: string): Promise<any> {
  const response = await apiClient.get(`/inspections/${inspectionId}`);
  return response.data;
}

/**
 * Get all inspections
 * @returns Promise with list of inspections
 */
export async function getInspections(): Promise<any[]> {
  const response = await apiClient.get("/inspections");
  return response.data;
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
export async function getMetrics(startDate: string, endDate: string): Promise<MetricsResponse> {
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
  limit?: number
): Promise<any[]> {
  const response = await apiClient.get("/inspections", {
    params: { startDate, endDate, limit },
  });
  return response.data;
}

export default apiClient;
