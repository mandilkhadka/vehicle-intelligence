/**
 * Damage feedback storage.
 *
 * Reviewers can confirm or correct each damage location, and add bbox-drawn
 * reports for damage the model missed entirely. The exports feed a future
 * fine-tuning loop — every label here is a future training example, so the
 * schema deliberately captures everything a YOLO label file needs (frame
 * path, bbox in image coordinates, type, severity).
 */

import { v4 as uuidv4 } from "uuid";
import { getDatabase } from "../db/init";

export type FeedbackVerdict =
  | "confirmed"
  | "wrong_type"
  | "false_positive"
  | "missed_severity";

export interface DamageFeedbackRecord {
  id: string;
  inspection_id: string;
  location_index: number;
  verdict: FeedbackVerdict;
  corrected_type?: string;
  corrected_severity?: string;
  note?: string;
  reviewer?: string;
  created_at: string;
}

export interface MissingDamageRecord {
  id: string;
  inspection_id: string;
  frame_path?: string;
  bbox?: string;
  type?: string;
  severity?: string;
  part?: string;
  note?: string;
  reviewer?: string;
  created_at: string;
}

export function createDamageFeedback(input: {
  inspectionId: string;
  locationIndex: number;
  verdict: FeedbackVerdict;
  correctedType?: string;
  correctedSeverity?: string;
  note?: string;
  reviewer?: string;
}): DamageFeedbackRecord {
  const db = getDatabase();
  const id = uuidv4();
  // (inspection_id, location_index) is the documented feedback key — a
  // re-review of the same location updates the existing verdict in place
  // instead of accumulating duplicate rows that would skew training exports.
  db.prepare(
    `INSERT INTO damage_feedback
        (id, inspection_id, location_index, verdict, corrected_type, corrected_severity, note, reviewer)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?)
     ON CONFLICT(inspection_id, location_index) DO UPDATE SET
        verdict = excluded.verdict,
        corrected_type = excluded.corrected_type,
        corrected_severity = excluded.corrected_severity,
        note = excluded.note,
        reviewer = excluded.reviewer,
        created_at = CURRENT_TIMESTAMP`,
  ).run(
    id,
    input.inspectionId,
    input.locationIndex,
    input.verdict,
    input.correctedType ?? null,
    input.correctedSeverity ?? null,
    input.note ?? null,
    input.reviewer ?? null,
  );
  // On conflict the existing row keeps its original id, so fetch by key.
  const record = db
    .prepare(
      "SELECT * FROM damage_feedback WHERE inspection_id = ? AND location_index = ?",
    )
    .get(input.inspectionId, input.locationIndex) as
    | DamageFeedbackRecord
    | undefined;
  if (!record) {
    throw new Error(
      `Damage feedback for ${input.inspectionId}:${input.locationIndex} missing after upsert`,
    );
  }
  return record;
}

export function getDamageFeedbackById(id: string): DamageFeedbackRecord | undefined {
  const db = getDatabase();
  return db
    .prepare("SELECT * FROM damage_feedback WHERE id = ?")
    .get(id) as DamageFeedbackRecord | undefined;
}

export function listFeedbackForInspection(inspectionId: string): DamageFeedbackRecord[] {
  const db = getDatabase();
  return db
    .prepare(
      "SELECT * FROM damage_feedback WHERE inspection_id = ? ORDER BY created_at DESC",
    )
    .all(inspectionId) as DamageFeedbackRecord[];
}

export function deleteDamageFeedback(id: string): boolean {
  const db = getDatabase();
  const result = db.prepare("DELETE FROM damage_feedback WHERE id = ?").run(id);
  return Number(result.changes) > 0;
}

export function createMissingDamage(input: {
  inspectionId: string;
  framePath?: string;
  bbox?: number[];
  type?: string;
  severity?: string;
  part?: string;
  note?: string;
  reviewer?: string;
}): MissingDamageRecord {
  const db = getDatabase();
  const id = uuidv4();
  db.prepare(
    `INSERT INTO damage_missing_reports
        (id, inspection_id, frame_path, bbox, type, severity, part, note, reviewer)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
  ).run(
    id,
    input.inspectionId,
    input.framePath ?? null,
    input.bbox ? JSON.stringify(input.bbox) : null,
    input.type ?? null,
    input.severity ?? null,
    input.part ?? null,
    input.note ?? null,
    input.reviewer ?? null,
  );
  const record = getMissingDamageById(id);
  if (!record) {
    throw new Error(`Missing-damage report ${id} missing immediately after insert`);
  }
  return record;
}

export function getMissingDamageById(id: string): MissingDamageRecord | undefined {
  const db = getDatabase();
  return db
    .prepare("SELECT * FROM damage_missing_reports WHERE id = ?")
    .get(id) as MissingDamageRecord | undefined;
}

export function listMissingForInspection(inspectionId: string): MissingDamageRecord[] {
  const db = getDatabase();
  return db
    .prepare(
      "SELECT * FROM damage_missing_reports WHERE inspection_id = ? ORDER BY created_at DESC",
    )
    .all(inspectionId) as MissingDamageRecord[];
}

export function deleteMissingDamage(id: string): boolean {
  const db = getDatabase();
  const result = db
    .prepare("DELETE FROM damage_missing_reports WHERE id = ?")
    .run(id);
  return Number(result.changes) > 0;
}

export interface FeedbackExportRow {
  inspection_id: string;
  source: "feedback" | "missing";
  feedback_id: string;
  location_index?: number;
  verdict?: string;
  corrected_type?: string;
  corrected_severity?: string;
  reported_type?: string;
  reported_severity?: string;
  reported_part?: string;
  frame_path?: string;
  bbox?: string;
  note?: string;
  reviewer?: string;
  created_at: string;
  damage_summary?: string;
}

/**
 * Joined export for the training-set builder.
 *
 * `since` is compared via datetime(?): created_at is SQLite's
 * 'YYYY-MM-DD HH:MM:SS' space format while callers pass ISO 'T'/'Z'
 * timestamps — a raw string compare would silently drop every row created on
 * the since-date itself ('T' sorts after ' '). datetime() normalizes ISO
 * input to space format, and datetime(NULL) is NULL so the `? IS NULL OR`
 * guard still short-circuits.
 */
export function exportFeedbackSince(sinceISO?: string): FeedbackExportRow[] {
  const db = getDatabase();
  const params: (string | null)[] = [sinceISO ?? null, sinceISO ?? null];
  const feedbackRows = db
    .prepare(
      `SELECT
          df.inspection_id AS inspection_id,
          'feedback' AS source,
          df.id AS feedback_id,
          df.location_index AS location_index,
          df.verdict AS verdict,
          df.corrected_type AS corrected_type,
          df.corrected_severity AS corrected_severity,
          NULL AS reported_type,
          NULL AS reported_severity,
          NULL AS reported_part,
          NULL AS frame_path,
          NULL AS bbox,
          df.note AS note,
          df.reviewer AS reviewer,
          df.created_at AS created_at,
          i.damage_summary AS damage_summary
       FROM damage_feedback df
       LEFT JOIN inspections i ON i.id = df.inspection_id
       WHERE ? IS NULL OR df.created_at >= datetime(?)`,
    )
    .all(params[0], params[1]) as FeedbackExportRow[];

  const missingRows = db
    .prepare(
      `SELECT
          dm.inspection_id AS inspection_id,
          'missing' AS source,
          dm.id AS feedback_id,
          NULL AS location_index,
          NULL AS verdict,
          NULL AS corrected_type,
          NULL AS corrected_severity,
          dm.type AS reported_type,
          dm.severity AS reported_severity,
          dm.part AS reported_part,
          dm.frame_path AS frame_path,
          dm.bbox AS bbox,
          dm.note AS note,
          dm.reviewer AS reviewer,
          dm.created_at AS created_at,
          i.damage_summary AS damage_summary
       FROM damage_missing_reports dm
       LEFT JOIN inspections i ON i.id = dm.inspection_id
       WHERE ? IS NULL OR dm.created_at >= datetime(?)`,
    )
    .all(params[0], params[1]) as FeedbackExportRow[];

  return [...feedbackRows, ...missingRows].sort((a, b) =>
    a.created_at.localeCompare(b.created_at),
  );
}

export interface UncertainDetection {
  inspection_id: string;
  location_index: number;
  type?: string;
  part?: string;
  part_label?: string;
  severity?: string;
  confidence: number;
  uncertainty: number;
  snapshot?: string;
  frame?: string;
  has_feedback: boolean;
  created_at: string;
}

/**
 * Scan all completed inspections, parse their damage_summary JSON, and
 * surface unreviewed locations ordered by |confidence - 0.5| ascending.
 * Used by the /review page as the active-learning queue.
 *
 * We do this in JS instead of SQL because damage_summary is a JSON blob,
 * not normalized columns. For the volumes a single SQLite-backed install
 * sees, this is fine.
 */
export function listUncertainDetections(limit = 100): UncertainDetection[] {
  const db = getDatabase();
  const inspections = db
    .prepare(
      `SELECT i.id AS id, i.damage_summary AS damage_summary, i.created_at AS created_at
         FROM inspections i
        WHERE i.damage_summary IS NOT NULL AND i.damage_summary != ''`,
    )
    .all() as Array<{ id: string; damage_summary: string; created_at: string }>;

  const feedbackKeys = new Set(
    (
      db
        .prepare("SELECT inspection_id, location_index FROM damage_feedback")
        .all() as Array<{ inspection_id: string; location_index: number }>
    ).map((r) => `${r.inspection_id}:${r.location_index}`),
  );

  interface ParsedLocation {
    type?: string;
    part?: string;
    part_label?: string;
    severity?: string;
    confidence?: number;
    snapshot?: string;
    frame?: string;
  }

  const stringOrUndefined = (v: unknown): string | undefined =>
    typeof v === "string" ? v : undefined;

  const out: UncertainDetection[] = [];
  for (const row of inspections) {
    let summary: unknown;
    try {
      summary = JSON.parse(row.damage_summary);
    } catch {
      continue;
    }
    const locations: unknown[] =
      summary &&
      typeof summary === "object" &&
      Array.isArray((summary as { locations?: unknown }).locations)
        ? (summary as { locations: unknown[] }).locations
        : [];
    locations.forEach((rawLoc: unknown, idx: number) => {
      const loc: Partial<ParsedLocation> =
        typeof rawLoc === "object" && rawLoc !== null
          ? (rawLoc as Partial<ParsedLocation>)
          : {};
      const conf = typeof loc.confidence === "number" ? loc.confidence : 0;
      const key = `${row.id}:${idx}`;
      const hasFeedback = feedbackKeys.has(key);
      out.push({
        inspection_id: row.id,
        location_index: idx,
        type: stringOrUndefined(loc.type),
        part: stringOrUndefined(loc.part),
        part_label: stringOrUndefined(loc.part_label),
        severity: stringOrUndefined(loc.severity),
        confidence: conf,
        uncertainty: Math.abs(conf - 0.5),
        snapshot: stringOrUndefined(loc.snapshot),
        frame: stringOrUndefined(loc.frame),
        has_feedback: hasFeedback,
        created_at: row.created_at,
      });
    });
  }

  return out
    .filter((d) => !d.has_feedback)
    .sort((a, b) => a.uncertainty - b.uncertainty)
    .slice(0, limit);
}
