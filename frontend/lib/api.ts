/**
 * API client for communicating with the backend
 * Handles all HTTP requests to the backend API
 */

import axios from "axios";

// Base URL for the backend API
// In production, this would be an environment variable
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:3001/api";

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
 * @param onProgress - Optional callback for upload progress
 * @returns Promise with job ID and file info
 */
export async function uploadVideo(
  file: File,
  onProgress?: (progress: number) => void
): Promise<{ jobId: string; fileId: string }> {
  const formData = new FormData();
  formData.append("video", file);

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
  error?: string;
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

export default apiClient;
