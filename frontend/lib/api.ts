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
  vehicleIdentity?: {
    vehicle_identity_source?: string;
    vehicle_brand?: string;
    vehicle_model?: string;
    vehicle_year?: string;
    vehicle_variant?: string;
    vehicle_type?: string;
    vehicle_category?: string;
    vin?: string;
    registration?: string;
  },
): Promise<{
  jobId: string;
  fileId: string;
  odometerImageUploaded?: boolean;
  vehicleIdentityEvidenceUploaded?: boolean;
}> {
  const formData = new FormData();
  formData.append("video", file);
  if (odometerImage) {
    formData.append("odometer_image", odometerImage);
  }
  if (vehicleIdentity) {
    Object.entries(vehicleIdentity).forEach(([key, value]) => {
      if (value && value.trim()) {
        formData.append(key, value.trim());
      }
    });
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
  vehicle_year?: string;
  vehicle_variant?: string;
  vehicle_confidence?: number;
  vehicle_info?: string | Record<string, unknown>;
  odometer_value?: number;
  odometer_confidence?: number;
  speedometer_image_path?: string;
  odometer_info?: {
    value?: number | null;
    confidence?: number;
    speedometer_image_path?: string | null;
    source_frame_index?: number | null;
    timestamp_seconds?: number | null;
    source_frame_path?: string | null;
    organized_frame_path?: string | null;
    crop_path?: string | null;
    readout_crop_path?: string | null;
    notes?: string | null;
    reason?: string | null;
    reasoning?: string | null;
    alternatives?: Array<{
      value?: number | null;
      confidence?: number;
      occurrences?: number;
      digit_count?: number;
      preprocessing?: string[];
    }>;
  } | string;
  damage_summary?: string | Record<string, unknown>;
  scratches_detected?: number;
  dents_detected?: number;
  rust_detected?: number;
  damage_severity?: string;
  exhaust_type?: string;
  exhaust_confidence?: number;
  exhaust_image_path?: string;
  inspection_report?: string | (Record<string, unknown> & {
    pipeline_audit?: PipelineAudit;
    frame_analysis?: FrameAnalysis;
    inspection_analysis?: InspectionAnalysis;
    local_modification_analysis?: {
      available: boolean;
      method?: string;
      reason?: string;
      summary?: string;
      items: Array<{
        part: string;
        status: "stock" | "modified" | "unknown";
        confidence?: number;
        source?: string;
        frame?: string | null;
        view?: string;
        frame_index?: number;
        source_frame_index?: number;
        timestamp_seconds?: number;
        notes?: string;
      }>;
    };
  });
  extracted_frames?: string | string[];
  created_at: string;
  updated_at: string;
}

export interface PipelineAuditCheck {
  id: string;
  requirement: string;
  passed: boolean;
  evidence: Record<string, unknown>;
}

export interface PipelineAudit {
  status: "complete" | "incomplete";
  passed: boolean;
  source?: string;
  thresholds?: Record<string, number>;
  checks: PipelineAuditCheck[];
  missing: string[];
}

export interface FrameAnalysisItem {
  view: string;
  frame: string;
  frame_index?: number;
  extracted_index?: number;
  source_frame_index?: number;
  timestamp_seconds?: number;
  organized_path?: string;
  crop_path?: string;
  readout_crop_path?: string;
  score?: number;
  quality_score?: number;
  vehicle_ratio?: number;
  dashboard_score?: number;
  clip_score?: number;
  temporal_score?: number;
  high_confidence?: boolean;
  semantic_source?: string;
  candidate_role?: string;
}

export interface FrameAnalysis {
  angle_shots: Record<string, FrameAnalysisItem>;
  dashboard_candidates: FrameAnalysisItem[];
  representative_frames: FrameAnalysisItem[];
  coverage: {
    required_views: string[];
    present_views: string[];
    high_confidence_views?: string[];
    low_confidence_views?: string[];
    missing_views: string[];
    ratio: number;
    high_confidence_ratio?: number;
  };
  frames_analyzed: number;
  frames_total: number;
  extraction_metadata?: {
    video_fps?: number | null;
    total_source_frames?: number | null;
    video_duration_seconds?: number | null;
    first_timestamp_seconds?: number | null;
    last_timestamp_seconds?: number | null;
    temporal_coverage_ratio?: number | null;
    frames_extracted?: number;
    skipped_blurry?: number;
    skipped_duplicate?: number;
    frame_interval?: number;
  };
  method: string;
}

export interface InspectionAnalysisImage {
  id: string;
  frame: string;
  preview_path?: string;
  section: string;
  group: "exterior" | "interior" | "closeup" | "review";
  source_view?: string;
  confidence?: number;
  quality_score?: number;
  vehicle_ratio?: number;
  foreground_bbox?: number[] | null;
  dashboard_score?: number;
  timestamp_seconds?: number;
  high_confidence?: boolean;
  tags?: string[];
}

export interface InspectionAnalysis {
  available: boolean;
  generated_at?: string;
  provider?: string;
  section_order: string[];
  sections: Record<string, InspectionAnalysisImage[]>;
  images: InspectionAnalysisImage[];
  rejected_images: InspectionAnalysisImage[];
  vehicle?: Record<string, unknown>;
  damage_detections?: Array<Record<string, unknown>>;
  consistency?: Record<string, unknown>;
  stages?: Record<string, unknown>;
  raw_model_responses?: Record<string, unknown>;
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

export interface VehicleIdentityEvidence {
  source?: string;
  vehicle_identity_source?: string;
  brand?: string;
  vehicle_brand?: string;
  model?: string;
  vehicle_model?: string;
  year?: string;
  vehicle_year?: string;
  variant?: string;
  vehicle_variant?: string;
  type?: string;
  vehicle_type?: string;
  vehicle_category?: string;
  category?: string;
  color?: string;
  vehicle_color?: string;
  vin?: string;
  registration?: string;
  confidence?: number;
}

/**
 * Merge trusted identity evidence into an existing inspection.
 */
export async function updateInspectionIdentity(
  inspectionId: string,
  evidence: VehicleIdentityEvidence,
): Promise<InspectionRecord> {
  const response = await apiClient.put(
    `/inspections/${inspectionId}/identity`,
    evidence,
  );
  return response.data.data;
}

export interface VlmEvidence {
  available: boolean;
  provider?: string;
  reason?: string;
  vehicle?: Record<string, unknown>;
  overall_condition?: string;
  damage_items?: Array<Record<string, unknown>>;
  modification_items?: Array<Record<string, unknown>>;
  [key: string]: unknown;
}

/**
 * Merge externally generated VLM evidence into an existing inspection.
 */
export async function updateInspectionVlmEvidence(
  inspectionId: string,
  evidence: VlmEvidence,
): Promise<InspectionRecord> {
  const response = await apiClient.put(
    `/inspections/${inspectionId}/vlm`,
    evidence,
  );
  return response.data.data;
}

/**
 * Rerun live VLM analysis for an existing inspection after provider keys/quota are available.
 */
export async function retryInspectionVlmAnalysis(
  inspectionId: string,
): Promise<InspectionRecord> {
  const response = await apiClient.post(
    `/inspections/${inspectionId}/retry-vlm`,
  );
  return response.data.data;
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
    cracks: number;
    paint_damage: number;
    wheel_damage?: number;
    broken_lights?: number;
    missing_parts?: number;
    panel_misalignment?: number;
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
