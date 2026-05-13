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
    confidence?: number;
  } | null;
  odometer_reading?: string | null;
  odometer?: {
    value: number | null;
    confidence: number;
    speedometer_image_path?: string | null;
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
  } | null;
  damage_summary?: {
    scratches: DamageItem[];
    dents: DamageItem[];
    rust: DamageItem[];
    cracks?: DamageItem[];
    paint_damage?: DamageItem[];
  } | null;
  damage?: {
    scratches: { count: number; detected: boolean };
    dents: { count: number; detected: boolean };
    rust: { count: number; detected: boolean };
    cracks?: { count: number; detected: boolean };
    paint_damage?: { count: number; detected: boolean };
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
  frame_analysis?: FrameAnalysis | null;
  extracted_frames?: string[];
  frames?: string[];
  inspection_report?: string | null;
  report?: {
    summary: string;
    recommendations: string[];
    frame_analysis?: FrameAnalysis;
    pipeline_audit?: PipelineAudit;
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
