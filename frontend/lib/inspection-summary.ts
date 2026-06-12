/**
 * Shared transform from a raw backend inspection record to the row shape
 * the history table and the dashboard "Recent Inspections" list render.
 * Keeping it in one place keeps the two lists (and the damage taxonomy
 * they count) from drifting apart.
 */

import { uploadSrc } from "@/lib/format";
import { safeParseJsonOrValue } from "@/lib/utils/safe-json";
import {
  getAuditBadgeState,
  getInspectionPipelineAudit,
  type AuditBadgeState,
} from "@/lib/inspection-audit";

/**
 * Every damage category the ML pipeline emits. Must stay in sync with
 * DamageInfo and the backend MetricsResponse.damageBreakdown keys.
 */
export const DAMAGE_CATEGORY_KEYS = [
  "scratches",
  "dents",
  "rust",
  "cracks",
  "paint_damage",
  "wheel_damage",
  "broken_lights",
  "missing_parts",
  "panel_misalignment",
] as const;

/** Total issue count across all damage categories. */
export function countDamageIssues(
  damage: Record<string, { count?: number } | undefined>,
): number {
  return DAMAGE_CATEGORY_KEYS.reduce(
    (total, key) => total + (damage?.[key]?.count || 0),
    0,
  );
}

export interface InspectionListItem {
  id: string;
  /** Display string like "2024 Toyota Sienta Hybrid Z", or the fallback. */
  vehicle: string;
  brand: string;
  status: string;
  auditState: AuditBadgeState;
  issues: number;
  /** Parsed creation date (epoch 0 when missing, for stable sorting). */
  date: Date | null;
  odometer: number | string;
  /** Vehicle identification confidence, 0..1. */
  confidence: number;
  /** First usable frame as a full image URL, or null. */
  image: string | null;
}

function isReal(v: unknown): v is string {
  return typeof v === "string" && v.trim() !== "" && v !== "Unknown";
}

export function toInspectionListItem(
  insp: Record<string, any>,
  { fallbackVehicleLabel = "Unidentified" }: { fallbackVehicleLabel?: string } = {},
): InspectionListItem {
  const vehicleInfo = safeParseJsonOrValue<Record<string, any>>(
    insp.vehicle_info,
    {},
  );
  const damage = safeParseJsonOrValue<Record<string, any>>(
    insp.damage_summary,
    {},
  );
  const frames = safeParseJsonOrValue<string[]>(insp.extracted_frames, []);

  const brand =
    (isReal(vehicleInfo.brand) && vehicleInfo.brand) ||
    (isReal(insp.vehicle_brand) && insp.vehicle_brand) ||
    "";
  const model =
    (isReal(vehicleInfo.model) && vehicleInfo.model) ||
    (isReal(insp.vehicle_model) && insp.vehicle_model) ||
    "";
  const year = vehicleInfo.year
    ? String(vehicleInfo.year)
    : (isReal(insp.vehicle_year) && insp.vehicle_year) || "";
  const variant = vehicleInfo.variant
    ? String(vehicleInfo.variant)
    : (isReal(insp.vehicle_variant) && insp.vehicle_variant) || "";
  const vehicle =
    [year, brand, model, variant].filter(Boolean).join(" ").trim() ||
    fallbackVehicleLabel;

  const confidence =
    (typeof vehicleInfo.confidence === "number" && vehicleInfo.confidence) ||
    (typeof insp.vehicle_confidence === "number" && insp.vehicle_confidence) ||
    0;

  // Skip known-dead paths from old MOCK_MODE rows.
  const firstFrame = frames[0];
  const image =
    typeof firstFrame === "string" && !firstFrame.startsWith("frames/sample/")
      ? uploadSrc(firstFrame)
      : null;

  return {
    id: insp.id,
    vehicle,
    brand: brand || "—",
    status: insp.job_status || "completed",
    auditState: getAuditBadgeState(getInspectionPipelineAudit(insp as any)),
    issues: countDamageIssues(damage),
    date: insp.created_at ? new Date(insp.created_at) : null,
    odometer: insp.odometer_value || "N/A",
    confidence,
    image,
  };
}
