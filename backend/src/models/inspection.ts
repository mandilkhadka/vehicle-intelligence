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

/**
 * Metrics response interface
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
 * Get inspections metrics for a date range
 */
export function getInspectionMetrics(startDate: string, endDate: string): MetricsResponse {
  const db = getDatabase();

  // Summary stats
  const summaryStmt = db.prepare(`
    SELECT
      COUNT(*) as totalInspections,
      COUNT(DISTINCT vehicle_brand || '-' || COALESCE(vehicle_model, '')) as uniqueVehicles,
      COALESCE(SUM(scratches_detected), 0) + COALESCE(SUM(dents_detected), 0) + COALESCE(SUM(rust_detected), 0) as totalIssues
    FROM inspections
    WHERE created_at >= ? AND created_at < datetime(?, '+1 day')
  `);
  const summaryRow = summaryStmt.get(startDate, endDate) as {
    totalInspections: number;
    uniqueVehicles: number;
    totalIssues: number;
  };

  // Daily trend
  const trendStmt = db.prepare(`
    SELECT
      DATE(created_at) as date,
      COALESCE(SUM(scratches_detected), 0) + COALESCE(SUM(dents_detected), 0) + COALESCE(SUM(rust_detected), 0) as issues
    FROM inspections
    WHERE created_at >= ? AND created_at < datetime(?, '+1 day')
    GROUP BY DATE(created_at)
    ORDER BY date
  `);
  const trendRows = trendStmt.all(startDate, endDate) as Array<{
    date: string;
    issues: number;
  }>;

  // Fill in missing dates with zeros
  const dailyTrend = fillMissingDates(trendRows, startDate, endDate);

  // Damage breakdown
  const damageStmt = db.prepare(`
    SELECT
      COALESCE(SUM(scratches_detected), 0) as scratches,
      COALESCE(SUM(dents_detected), 0) as dents,
      COALESCE(SUM(rust_detected), 0) as rust
    FROM inspections
    WHERE created_at >= ? AND created_at < datetime(?, '+1 day')
  `);
  const damageRow = damageStmt.get(startDate, endDate) as {
    scratches: number;
    dents: number;
    rust: number;
  };

  // Vehicle breakdown (top 5 + Other)
  const vehicleStmt = db.prepare(`
    SELECT
      COALESCE(vehicle_brand, 'Unknown') as brand,
      COUNT(*) as count
    FROM inspections
    WHERE created_at >= ? AND created_at < datetime(?, '+1 day')
    GROUP BY vehicle_brand
    ORDER BY count DESC
    LIMIT 6
  `);
  const vehicleRows = vehicleStmt.all(startDate, endDate) as Array<{
    brand: string;
    count: number;
  }>;

  // If more than 5 brands, group extras as "Other"
  let vehicleBreakdown = vehicleRows;
  if (vehicleRows.length > 5) {
    const top5 = vehicleRows.slice(0, 5);
    const otherCount = vehicleRows.slice(5).reduce((sum, row) => sum + row.count, 0);
    vehicleBreakdown = [...top5, { brand: "Other", count: otherCount }];
  }

  return {
    summary: {
      totalInspections: summaryRow.totalInspections || 0,
      uniqueVehicles: summaryRow.uniqueVehicles || 0,
      totalIssues: summaryRow.totalIssues || 0,
      avgProcessingTime: 45, // Placeholder - would need actual processing time tracking
    },
    dailyTrend,
    damageBreakdown: {
      scratches: damageRow.scratches || 0,
      dents: damageRow.dents || 0,
      rust: damageRow.rust || 0,
    },
    vehicleBreakdown,
  };
}

/**
 * Fill missing dates with zero values
 */
function fillMissingDates(
  data: Array<{ date: string; issues: number }>,
  startDate: string,
  endDate: string
): Array<{ date: string; issues: number }> {
  const result: Array<{ date: string; issues: number }> = [];
  const dataMap = new Map(data.map((d) => [d.date, d.issues]));

  const start = new Date(startDate);
  const end = new Date(endDate);

  for (let d = new Date(start); d <= end; d.setDate(d.getDate() + 1)) {
    const dateStr = d.toISOString().split("T")[0];
    result.push({
      date: dateStr,
      issues: dataMap.get(dateStr) || 0,
    });
  }

  return result;
}

/**
 * Get inspections filtered by date range
 */
export function getInspectionsByDateRange(
  startDate: string,
  endDate: string,
  limit?: number
): InspectionRecord[] {
  const db = getDatabase();
  let query = `
    SELECT * FROM inspections
    WHERE created_at >= ? AND created_at < datetime(?, '+1 day')
    ORDER BY created_at DESC
  `;

  if (limit) {
    query += ` LIMIT ${limit}`;
  }

  const stmt = db.prepare(query);
  return stmt.all(startDate, endDate) as InspectionRecord[];
}
