/**
 * Shared TypeScript types and interfaces
 * Used across frontend and backend for type safety
 */

/**
 * Vehicle type enumeration
 */
export type VehicleType = "car" | "bike" | "motorcycle" | "truck" | "suv";

/**
 * Job status enumeration
 */
export type JobStatus = "pending" | "processing" | "completed" | "failed";

/**
 * Damage severity enumeration
 */
export type DamageSeverity = "low" | "medium" | "high";

/**
 * Exhaust type enumeration
 */
export type ExhaustType = "stock" | "modified";

/**
 * Vehicle identification information
 */
export interface VehicleInfo {
  type: VehicleType;
  brand: string;
  model: string;
  year?: string;
  variant?: string;
  vehicle_category?: string;
  year_range?: string;
  generation?: string;
  variant_candidates?: string[];
  variant_candidate?: string;
  variant_confidence?: number;
  variant_candidates_ranked?: Array<{
    variant: string;
    confidence: number;
  }>;
  model_confidence?: number;
  model_candidates?: Array<{
    model: string;
    confidence: number;
  }>;
  identity_notes?: string;
  color?: string;
  confidence: number;
}

/**
 * Odometer reading information
 */
export interface OdometerInfo {
  value: number | null;
  confidence: number;
  speedometer_image_path: string | null;
  source_frame_index?: number | null;
  timestamp_seconds?: number | null;
  source_frame_path?: string | null;
  organized_frame_path?: string | null;
  crop_path?: string | null;
  readout_crop_path?: string | null;
  alternatives?: Array<{
    value?: number | null;
    confidence?: number;
    occurrences?: number;
    digit_count?: number;
    preprocessing?: string[];
  }>;
}

/**
 * Damage detection results
 */
export interface DamageInfo {
  scratches: {
    count: number;
    detected: boolean;
  };
  dents: {
    count: number;
    detected: boolean;
  };
  rust: {
    count: number;
    detected: boolean;
  };
  cracks?: {
    count: number;
    detected: boolean;
  };
  paint_damage?: {
    count: number;
    detected: boolean;
  };
  wheel_damage?: {
    count: number;
    detected: boolean;
  };
  broken_lights?: {
    count: number;
    detected: boolean;
  };
  missing_parts?: {
    count: number;
    detected: boolean;
  };
  panel_misalignment?: {
    count: number;
    detected: boolean;
  };
  severity: DamageSeverity;
  locations?: Array<{
    type: string;
    frame: string;
    snapshot?: string;
    confidence: number;
    bbox?: [number, number, number, number];
    /** Normalized (0-1) segmentation polygon [[x, y], ...] from the damage model */
    mask?: Array<[number, number]>;
    /** Pixel dimensions of `frame`, for scaling bbox/mask overlays */
    frame_width?: number;
    frame_height?: number;
    /** "detector" (dedicated damage model) or "vlm" */
    source?: string;
    severity?: DamageSeverity;
    angle?: string;
    linked_view?: string;
    frame_index?: number;
    source_frame_index?: number;
    timestamp_seconds?: number;
  }>;
}

/**
 * Exhaust classification results
 */
export interface ExhaustInfo {
  type: ExhaustType;
  confidence: number;
}

/**
 * Runtime verification check for process/report completeness
 */
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

/**
 * Inspection report structure
 */
export interface InspectionReport {
  summary: string;
  vehicle_details: {
    type: string;
    brand: string;
    model: string;
    year?: string;
    variant?: string;
    vehicle_category?: string;
    year_range?: string;
    generation?: string;
    variant_candidates?: string[];
    variant_candidate?: string | null;
    variant_confidence?: number | null;
    variant_candidates_ranked?: Array<{
      variant: string;
      confidence: number;
    }>;
    model_confidence?: number | null;
    model_candidates?: Array<{
      model: string;
      confidence: number;
    }>;
    identity_notes?: string | null;
    color?: string;
    confidence?: number;
    condition: string;
  };
  odometer_reading: {
    value: number | null;
    status: string;
    confidence?: number | null;
    source_frame_index?: number | null;
    timestamp_seconds?: number | null;
    speedometer_image_path?: string | null;
    source_frame_path?: string | null;
    organized_frame_path?: string | null;
    crop_path?: string | null;
    readout_crop_path?: string | null;
    notes?: string | null;
    alternatives?: Array<{
      value?: number | null;
      confidence?: number;
      occurrences?: number;
      digit_count?: number;
      preprocessing?: string[];
    }>;
  };
  damage_assessment: {
    overall_severity: DamageSeverity;
    details: string;
  };
  exhaust_status: {
    type: ExhaustType;
    notes: string;
  };
  visual_analysis?: {
    available: boolean;
    reason?: string | null;
  };
  modification_assessment?: {
    summary: string;
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
  frame_analysis?: FrameAnalysis;
  pipeline_audit?: PipelineAudit;
  recommendations: string[];
}

/**
 * Complete inspection data
 */
export interface InspectionData {
  id: string;
  job_id: string;
  file_id: string;
  vehicle_info?: VehicleInfo;
  odometer?: OdometerInfo;
  damage?: DamageInfo;
  exhaust?: ExhaustInfo;
  inspection_report?: InspectionReport;
  extracted_frames?: string[];
  created_at: string;
  updated_at: string;
}

/**
 * Job information
 */
export interface JobInfo {
  id: string;
  file_id: string;
  status: JobStatus;
  progress: number;
  error_message?: string;
  inspection_id?: string;
  created_at: string;
  updated_at: string;
}

/**
 * File upload response
 */
export interface UploadResponse {
  jobId: string;
  fileId: string;
  message: string;
}
