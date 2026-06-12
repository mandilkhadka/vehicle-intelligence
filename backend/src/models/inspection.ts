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
  vehicle_year?: string;
  vehicle_variant?: string;
  vehicle_confidence?: number;
  vehicle_info?: string;
  odometer_value?: number;
  odometer_confidence?: number;
  speedometer_image_path?: string;
  odometer_info?: string;
  damage_summary?: string;
  scratches_detected?: number;
  dents_detected?: number;
  rust_detected?: number;
  cracks_detected?: number;
  paint_damage_detected?: number;
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
    file.mime_type,
  );

  const created = getFileById(file.id);
  if (!created) {
    throw new Error(`File ${file.id} missing immediately after insert`);
  }
  return created;
}

/**
 * Get file by ID
 */
export function getFileById(id: string): FileRecord | undefined {
  const db = getDatabase();
  const stmt = db.prepare("SELECT * FROM files WHERE id = ?");
  return stmt.get(id) as FileRecord | undefined;
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

  const created = getJobById(job.id);
  if (!created) {
    throw new Error(`Job ${job.id} missing immediately after insert`);
  }
  return created;
}

/**
 * Get job by ID
 */
export function getJobById(id: string): JobRecord | undefined {
  const db = getDatabase();
  const stmt = db.prepare("SELECT * FROM jobs WHERE id = ?");
  return stmt.get(id) as JobRecord | undefined;
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
  },
): JobRecord {
  const db = getDatabase();
  const updatesList: string[] = [];
  const values: Array<string | number> = [];

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
    `UPDATE jobs SET ${updatesList.join(", ")} WHERE id = ?`,
  );
  stmt.run(...values);

  const updated = getJobById(id);
  if (!updated) {
    throw new Error(`Job ${id} not found while updating status`);
  }
  return updated;
}

/**
 * Touch a job's progress only while it is still `processing`.
 *
 * Used by the in-flight progress simulation so a job the reaper already
 * marked `failed` is never resurrected back to `processing` by a late tick.
 * Returns false when no row changed (job no longer processing).
 */
export function touchJobIfProcessing(id: string, progress?: number): boolean {
  const db = getDatabase();
  const result =
    progress === undefined
      ? db
          .prepare(
            `UPDATE jobs SET updated_at = CURRENT_TIMESTAMP
              WHERE id = ? AND status = 'processing'`,
          )
          .run(id)
      : db
          .prepare(
            `UPDATE jobs SET progress = ?, updated_at = CURRENT_TIMESTAMP
              WHERE id = ? AND status = 'processing'`,
          )
          .run(progress, id);
  return Number(result.changes) > 0;
}

/**
 * Flip a job to `completed` only if it is still `processing`.
 *
 * Guards against the reaper race: if a long ML call finally returns after the
 * periodic reaper already marked the job failed, we must not flip
 * failed -> completed. Returns false when no row changed.
 */
export function completeJobIfProcessing(id: string, inspectionId: string): boolean {
  const db = getDatabase();
  const result = db
    .prepare(
      `UPDATE jobs
          SET status = 'completed',
              progress = 100,
              inspection_id = ?,
              updated_at = CURRENT_TIMESTAMP
        WHERE id = ? AND status = 'processing'`,
    )
    .run(inspectionId, id);
  return Number(result.changes) > 0;
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

  const created = getInspectionById(inspection.id);
  if (!created) {
    throw new Error(`Inspection ${inspection.id} missing immediately after insert`);
  }
  return created;
}

/**
 * Get inspection by ID
 */
export function getInspectionById(id: string): InspectionRecord | undefined {
  const db = getDatabase();
  const stmt = db.prepare("SELECT * FROM inspections WHERE id = ?");
  return stmt.get(id) as InspectionRecord | undefined;
}

/**
 * Update inspection with results
 */
export function updateInspection(
  id: string,
  updates: Partial<InspectionRecord>,
): InspectionRecord {
  const db = getDatabase();
  const updatesList: string[] = [];
  const values: Array<string | number | null> = [];

  // Build update statement dynamically
  const fields: (keyof InspectionRecord)[] = [
    "vehicle_type",
    "vehicle_brand",
    "vehicle_model",
    "vehicle_year",
    "vehicle_variant",
    "vehicle_confidence",
    "vehicle_info",
    "odometer_value",
    "odometer_confidence",
    "speedometer_image_path",
    "odometer_info",
    "damage_summary",
    "scratches_detected",
    "dents_detected",
    "rust_detected",
    "cracks_detected",
    "paint_damage_detected",
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
    `UPDATE inspections SET ${updatesList.join(", ")} WHERE id = ?`,
  );
  stmt.run(...values);

  const updated = getInspectionById(id);
  if (!updated) {
    throw new Error(`Inspection ${id} not found while updating`);
  }
  return updated;
}

/**
 * Return uploaded video paths for completed jobs whose inspection finished
 * more than `retentionDays` ago. The caller is expected to remove these files
 * from disk. Frames and snapshots under uploads/frames are kept so users can
 * still revisit their inspection report.
 */
export function listVideosEligibleForCleanup(retentionDays: number): Array<{ jobId: string; filePath: string }> {
  const db = getDatabase();
  const stmt = db.prepare(`
    SELECT j.id AS jobId, f.file_path AS filePath
      FROM jobs j
      INNER JOIN inspections i ON j.id = i.job_id
      INNER JOIN files f ON i.file_id = f.id
     WHERE j.status = 'completed'
       AND (julianday(CURRENT_TIMESTAMP) - julianday(i.updated_at)) > ?
       AND f.file_path IS NOT NULL
       AND f.file_path != ''
  `);
  return stmt.all(retentionDays) as Array<{ jobId: string; filePath: string }>;
}

/**
 * Return uploaded video paths for failed jobs older than `retentionDays`.
 *
 * processVideoJob deletes the video in its catch block, but that only runs if
 * the process survives — a job that died in a backend crash gets reaped to
 * `failed` and its video would otherwise leak forever. No inspections join:
 * a crash can predate the inspection row.
 */
export function listFailedJobVideosEligibleForCleanup(
  retentionDays: number,
): Array<{ jobId: string; filePath: string }> {
  const db = getDatabase();
  const stmt = db.prepare(`
    SELECT j.id AS jobId, f.file_path AS filePath
      FROM jobs j
      INNER JOIN files f ON f.id = j.file_id
     WHERE j.status = 'failed'
       AND (julianday(CURRENT_TIMESTAMP) - julianday(j.updated_at)) > ?
       AND f.file_path IS NOT NULL
       AND f.file_path != ''
  `);
  return stmt.all(retentionDays) as Array<{ jobId: string; filePath: string }>;
}

/**
 * Mark long-stuck jobs as failed.
 *
 * Job processing runs in-process; if the backend crashes mid-job, rows stay
 * in `pending` or `processing` forever and the frontend polls them
 * indefinitely. On startup (and optionally on a schedule) call this to flip
 * stale rows to `failed` with a recognizable error message so the UI moves on.
 */
export function reapStuckJobs(opts?: { processingMaxAgeMinutes?: number; pendingMaxAgeMinutes?: number }): number {
  const db = getDatabase();
  const processingMax = opts?.processingMaxAgeMinutes ?? 30;
  const pendingMax = opts?.pendingMaxAgeMinutes ?? 60;

  // SQLite's CURRENT_TIMESTAMP is UTC; updated_at is set on every status update.
  const stmt = db.prepare(`
    UPDATE jobs
       SET status = 'failed',
           error_message = COALESCE(error_message, ?),
           updated_at = CURRENT_TIMESTAMP
     WHERE (status = 'processing' AND (julianday(CURRENT_TIMESTAMP) - julianday(updated_at)) * 24 * 60 > ?)
        OR (status = 'pending'    AND (julianday(CURRENT_TIMESTAMP) - julianday(created_at)) * 24 * 60 > ?)
  `);
  const result = stmt.run(
    "Job abandoned (backend restarted while processing or never picked up)",
    processingMax,
    pendingMax,
  );
  return Number(result.changes) || 0;
}

/**
 * Get all inspections
 */
export function getAllInspections(): InspectionRecord[] {
  const db = getDatabase();
  const stmt = db.prepare(
    `SELECT i.*, j.status AS job_status
       FROM inspections i
       LEFT JOIN jobs j ON j.id = i.job_id
      ORDER BY i.created_at DESC`,
  );
  return stmt.all() as InspectionRecord[];
}

/**
 * List inspections with database-level pagination.
 * Pass limit = -1 for no limit (SQLite treats negative LIMIT as unlimited).
 */
export function listInspections(limit: number, offset: number): InspectionRecord[] {
  const db = getDatabase();
  const stmt = db.prepare(
    `SELECT i.*, j.status AS job_status
       FROM inspections i
       LEFT JOIN jobs j ON j.id = i.job_id
      ORDER BY i.created_at DESC
      LIMIT ? OFFSET ?`,
  );
  return stmt.all(limit, offset) as InspectionRecord[];
}

/**
 * Count all inspections (for pagination totals)
 */
export function countInspections(): number {
  const db = getDatabase();
  const row = db.prepare("SELECT COUNT(*) AS count FROM inspections").get() as {
    count: number;
  };
  return row.count;
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
    cracks: number;
    paint_damage: number;
  };
  vehicleBreakdown: Array<{
    brand: string;
    count: number;
  }>;
}

/**
 * Get inspections metrics for a date range
 */
export function getInspectionMetrics(
  startDate: string,
  endDate: string,
): MetricsResponse {
  const db = getDatabase();

  // Summary stats
  const summaryStmt = db.prepare(`
    SELECT
      COUNT(*) as totalInspections,
      COUNT(DISTINCT COALESCE(vehicle_brand, 'Unknown') || '-' || COALESCE(vehicle_model, '')) as uniqueVehicles,
      COALESCE(SUM(scratches_detected), 0) + COALESCE(SUM(dents_detected), 0) + COALESCE(SUM(rust_detected), 0) +
      COALESCE(SUM(cracks_detected), 0) + COALESCE(SUM(paint_damage_detected), 0) as totalIssues
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
      COALESCE(SUM(scratches_detected), 0) + COALESCE(SUM(dents_detected), 0) + COALESCE(SUM(rust_detected), 0) +
      COALESCE(SUM(cracks_detected), 0) + COALESCE(SUM(paint_damage_detected), 0) as issues
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
      COALESCE(SUM(rust_detected), 0) as rust,
      COALESCE(SUM(cracks_detected), 0) as cracks,
      COALESCE(SUM(paint_damage_detected), 0) as paint_damage
    FROM inspections
    WHERE created_at >= ? AND created_at < datetime(?, '+1 day')
  `);
  const damageRow = damageStmt.get(startDate, endDate) as {
    scratches: number;
    dents: number;
    rust: number;
    cracks: number;
    paint_damage: number;
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
    const otherCount = vehicleRows
      .slice(5)
      .reduce((sum, row) => sum + row.count, 0);
    vehicleBreakdown = [...top5, { brand: "Other", count: otherCount }];
  }

  // Average processing time (seconds) for completed jobs in date range
  const avgTimeStmt = db.prepare(`
    SELECT AVG(
      (julianday(j.updated_at) - julianday(j.created_at)) * 86400
    ) as avg_seconds
    FROM jobs j
    INNER JOIN inspections i ON j.id = i.job_id
    WHERE j.status = 'completed'
      AND i.created_at >= ? AND i.created_at < datetime(?, '+1 day')
  `);
  const avgTimeRow = avgTimeStmt.get(startDate, endDate) as {
    avg_seconds: number | null;
  };
  const avgProcessingTime = Math.round(avgTimeRow?.avg_seconds ?? 0);

  return {
    summary: {
      totalInspections: summaryRow.totalInspections || 0,
      uniqueVehicles: summaryRow.uniqueVehicles || 0,
      totalIssues: summaryRow.totalIssues || 0,
      avgProcessingTime,
    },
    dailyTrend,
    damageBreakdown: {
      scratches: damageRow.scratches || 0,
      dents: damageRow.dents || 0,
      rust: damageRow.rust || 0,
      cracks: damageRow.cracks || 0,
      paint_damage: damageRow.paint_damage || 0,
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
  endDate: string,
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

