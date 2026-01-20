/**
 * Database models for inspections
 * Provides functions to interact with inspection data
 */

import { getDatabase } from "../db/init";

export interface FileRecord {
  id: string;
  filename: string;
  original_filename: string;
  file_path: string;
  file_size: number;
  mime_type: string;
  created_at: string;
}

export interface JobRecord {
  id: string;
  file_id: string;
  status: "pending" | "processing" | "completed" | "failed";
  progress: number;
  error_message?: string;
  inspection_id?: string;
  created_at: string;
  updated_at: string;
}

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
  damage_summary?: string;
  scratches_detected?: number;
  dents_detected?: number;
  rust_detected?: number;
  damage_severity?: string;
  exhaust_type?: string;
  exhaust_confidence?: number;
  exhaust_image_path?: string;
  inspection_report?: string;
  extracted_frames?: string;
  created_at: string;
  updated_at: string;
}

/**
 * Create a new file record
 */
export function createFile(file: {
  id: string;
  filename: string;
  original_filename: string;
  file_path: string;
  file_size: number;
  mime_type: string;
}): FileRecord {
  const db = getDatabase();
  const stmt = db.prepare(`
    INSERT INTO files (id, filename, original_filename, file_path, file_size, mime_type)
    VALUES (?, ?, ?, ?, ?, ?)
  `);

  stmt.run(
    file.id,
    file.filename,
    file.original_filename,
    file.file_path,
    file.file_size,
    file.mime_type
  );

  return getFileById(file.id);
}

/**
 * Get file by ID
 */
export function getFileById(id: string): FileRecord {
  const db = getDatabase();
  const stmt = db.prepare("SELECT * FROM files WHERE id = ?");
  return stmt.get(id) as FileRecord;
}

/**
 * Create a new job record
 */
export function createJob(job: {
  id: string;
  file_id: string;
  status?: "pending" | "processing" | "completed" | "failed";
}): JobRecord {
  const db = getDatabase();
  const stmt = db.prepare(`
    INSERT INTO jobs (id, file_id, status)
    VALUES (?, ?, ?)
  `);

  stmt.run(job.id, job.file_id, job.status || "pending");

  return getJobById(job.id);
}

/**
 * Get job by ID
 */
export function getJobById(id: string): JobRecord {
  const db = getDatabase();
  const stmt = db.prepare("SELECT * FROM jobs WHERE id = ?");
  return stmt.get(id) as JobRecord;
}

/**
 * Update job status
 */
export function updateJobStatus(
  id: string,
  updates: {
    status?: "pending" | "processing" | "completed" | "failed";
    progress?: number;
    error_message?: string;
    inspection_id?: string;
  }
): JobRecord {
  const db = getDatabase();
  const updatesList: string[] = [];
  const values: any[] = [];

  if (updates.status !== undefined) {
    updatesList.push("status = ?");
    values.push(updates.status);
  }
  if (updates.progress !== undefined) {
    updatesList.push("progress = ?");
    values.push(updates.progress);
  }
  if (updates.error_message !== undefined) {
    updatesList.push("error_message = ?");
    values.push(updates.error_message);
  }
  if (updates.inspection_id !== undefined) {
    updatesList.push("inspection_id = ?");
    values.push(updates.inspection_id);
  }

  updatesList.push("updated_at = CURRENT_TIMESTAMP");
  values.push(id);

  const stmt = db.prepare(
    `UPDATE jobs SET ${updatesList.join(", ")} WHERE id = ?`
  );
  stmt.run(...values);

  return getJobById(id);
}

/**
 * Create a new inspection record
 */
export function createInspection(inspection: {
  id: string;
  job_id: string;
  file_id: string;
}): InspectionRecord {
  const db = getDatabase();
  const stmt = db.prepare(`
    INSERT INTO inspections (id, job_id, file_id)
    VALUES (?, ?, ?)
  `);

  stmt.run(inspection.id, inspection.job_id, inspection.file_id);

  return getInspectionById(inspection.id);
}

/**
 * Get inspection by ID
 */
export function getInspectionById(id: string): InspectionRecord {
  const db = getDatabase();
  const stmt = db.prepare("SELECT * FROM inspections WHERE id = ?");
  return stmt.get(id) as InspectionRecord;
}

/**
 * Update inspection with results
 */
export function updateInspection(
  id: string,
  updates: Partial<InspectionRecord>
): InspectionRecord {
  const db = getDatabase();
  const updatesList: string[] = [];
  const values: any[] = [];

  // Build update statement dynamically
  const fields: (keyof InspectionRecord)[] = [
    "vehicle_type",
    "vehicle_brand",
    "vehicle_model",
    "vehicle_confidence",
    "odometer_value",
    "odometer_confidence",
    "speedometer_image_path",
    "damage_summary",
    "scratches_detected",
    "dents_detected",
    "rust_detected",
    "damage_severity",
    "exhaust_type",
    "exhaust_confidence",
    "exhaust_image_path",
    "inspection_report",
    "extracted_frames",
  ];

  for (const field of fields) {
    if (updates[field] !== undefined) {
      updatesList.push(`${field} = ?`);
      values.push(updates[field]);
    }
  }

  updatesList.push("updated_at = CURRENT_TIMESTAMP");
  values.push(id);

  const stmt = db.prepare(
    `UPDATE inspections SET ${updatesList.join(", ")} WHERE id = ?`
  );
  stmt.run(...values);

  return getInspectionById(id);
}

/**
 * Get all inspections
 */
export function getAllInspections(): InspectionRecord[] {
  const db = getDatabase();
  const stmt = db.prepare("SELECT * FROM inspections ORDER BY created_at DESC");
  return stmt.all() as InspectionRecord[];
}
