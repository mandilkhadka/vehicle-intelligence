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
  severity: DamageSeverity;
  locations?: Array<{
    type: string;
    frame: string;
    snapshot?: string;
    confidence: number;
    bbox?: [number, number, number, number];
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
 * Inspection report structure
 */
export interface InspectionReport {
  summary: string;
  vehicle_details: {
    type: string;
    brand: string;
    model: string;
    condition: string;
  };
  odometer_reading: {
    value: number | null;
    status: string;
  };
  damage_assessment: {
    overall_severity: DamageSeverity;
    details: string;
  };
  exhaust_status: {
    type: ExhaustType;
    notes: string;
  };
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
