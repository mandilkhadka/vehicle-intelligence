"use client";

import { useEffect, useMemo, useState } from "react";
import Image from "next/image";
import { ChevronDown, ChevronRight, Info, Maximize2, ThumbsDown, ThumbsUp, Check, Loader2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import DamageOverlayViewer from "@/components/DamageOverlayViewer";
import {
  BACKEND_BASE_URL,
  listDamageFeedback,
  submitDamageFeedback,
  type FeedbackVerdict,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import { SEVERITY_RANK, formatCurrency, formatRange } from "@/lib/format";

interface EstimatedCost {
  low: number;
  high: number;
  midpoint: number;
  currency: string;
}

interface DamageLocation {
  type?: string;
  part?: string;
  part_label?: string;
  part_confidence?: number;
  frame?: string;
  snapshot?: string;
  confidence?: number;
  severity?: string;
  bbox?: [number, number, number, number];
  mask?: Array<[number, number]>;
  frame_width?: number;
  frame_height?: number;
  source?: string;
  rationale?: string | null;
  rationale_likely_real?: boolean | null;
  estimated_cost?: EstimatedCost | null;
}

interface TotalCost extends EstimatedCost {
  has_unknowns?: boolean;
  counted_locations?: number;
  unknown_locations?: number;
}

interface DamageInfoProps {
  damage?: {
    scratches?: { count?: number; detected?: boolean };
    dents?: { count?: number; detected?: boolean };
    rust?: { count?: number; detected?: boolean };
    cracks?: { count?: number; detected?: boolean };
    paint_damage?: { count?: number; detected?: boolean };
    wheel_damage?: { count?: number; detected?: boolean };
    broken_lights?: { count?: number; detected?: boolean };
    missing_parts?: { count?: number; detected?: boolean };
    panel_misalignment?: { count?: number; detected?: boolean };
    severity?: string;
    locations?: DamageLocation[];
    total_estimated_repair_cost?: TotalCost | null;
    rationale_available?: boolean;
    rationale_count?: number;
  };
  inspectionId?: string;
}

const SEVERITY_STYLES: Record<string, string> = {
  high: "border-destructive/40 bg-destructive/10 text-destructive",
  medium: "border-amber-500/40 bg-amber-500/10 text-amber-600 dark:text-amber-400",
  low: "border-emerald-500/40 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
};

function snapshotSrc(snapshot: string): string {
  const path = snapshot.startsWith("uploads/") ? snapshot : `uploads/${snapshot}`;
  return `${BACKEND_BASE_URL}/${path}`;
}

interface PartGroup {
  part: string;
  partLabel: string;
  locations: DamageLocation[];
  totalLow: number;
  totalHigh: number;
  currency: string;
  maxSeverity: string;
  hasCost: boolean;
}

function groupByPart(locations: DamageLocation[]): PartGroup[] {
  const map = new Map<string, PartGroup>();
  for (const loc of locations) {
    const part = loc.part || "unknown";
    const partLabel = loc.part_label || part.replace(/_/g, " ");
    let group = map.get(part);
    if (!group) {
      group = {
        part,
        partLabel,
        locations: [],
        totalLow: 0,
        totalHigh: 0,
        currency: loc.estimated_cost?.currency || "JPY",
        maxSeverity: "low",
        hasCost: false,
      };
      map.set(part, group);
    }
    group.locations.push(loc);
    if (loc.estimated_cost) {
      group.totalLow += loc.estimated_cost.low;
      group.totalHigh += loc.estimated_cost.high;
      group.hasCost = true;
      group.currency = loc.estimated_cost.currency;
    }
    const sev = (loc.severity || "low").toLowerCase();
    if ((SEVERITY_RANK[sev] ?? 0) > (SEVERITY_RANK[group.maxSeverity] ?? 0)) {
      group.maxSeverity = sev;
    }
  }
  return Array.from(map.values()).sort((a, b) => {
    const rankDiff = (SEVERITY_RANK[b.maxSeverity] ?? 0) - (SEVERITY_RANK[a.maxSeverity] ?? 0);
    if (rankDiff !== 0) return rankDiff;
    return b.totalHigh - a.totalHigh;
  });
}

export default function DamageInfo({ damage, inspectionId }: DamageInfoProps) {
  const [minConfidence, setMinConfidence] = useState(0.5);
  const [expandedPart, setExpandedPart] = useState<string | null>(null);
  const [viewerLocation, setViewerLocation] = useState<DamageLocation | null>(null);

  const allLocations = damage?.locations ?? [];
  const filteredLocations = useMemo(
    () => allLocations.filter((l) => (l.confidence ?? 0) >= minConfidence),
    [allLocations, minConfidence],
  );
  // We always group on the ORIGINAL location list so feedback indices stay
  // stable across filter changes. The filter only hides cards visually.
  const indexedLocations = useMemo(
    () =>
      allLocations.map((loc, idx) => ({
        ...loc,
        __originalIndex: idx,
      })) as Array<DamageLocation & { __originalIndex: number }>,
    [allLocations],
  );
  const visibleIndexedLocations = useMemo(
    () => indexedLocations.filter((l) => (l.confidence ?? 0) >= minConfidence),
    [indexedLocations, minConfidence],
  );
  const partGroups = useMemo(() => groupByPart(visibleIndexedLocations as any), [visibleIndexedLocations]);

  // Feedback state — { [locationIndex]: { verdict, pending? } }
  const [feedbackByIndex, setFeedbackByIndex] = useState<
    Record<number, { verdict: FeedbackVerdict; pending?: boolean; id?: string }>
  >({});

  useEffect(() => {
    if (!inspectionId) return;
    let cancelled = false;
    listDamageFeedback(inspectionId)
      .then((rows) => {
        if (cancelled) return;
        const map: Record<number, { verdict: FeedbackVerdict; id?: string }> = {};
        // Most recent verdict per location wins.
        for (const row of rows) {
          map[row.location_index] = { verdict: row.verdict, id: row.id };
        }
        setFeedbackByIndex(map);
      })
      .catch(() => {
        // Non-critical — feedback is best-effort, hide silent fetch errors.
      });
    return () => {
      cancelled = true;
    };
  }, [inspectionId]);

  const recordVerdict = async (locationIndex: number, verdict: FeedbackVerdict) => {
    if (!inspectionId) return;
    setFeedbackByIndex((prev) => ({
      ...prev,
      [locationIndex]: { verdict, pending: true },
    }));
    try {
      const record = await submitDamageFeedback(inspectionId, {
        location_index: locationIndex,
        verdict,
      });
      setFeedbackByIndex((prev) => ({
        ...prev,
        [locationIndex]: { verdict: record.verdict, id: record.id },
      }));
    } catch (err) {
      console.error("Failed to submit feedback", err);
      setFeedbackByIndex((prev) => {
        const next = { ...prev };
        delete next[locationIndex];
        return next;
      });
    }
  };

  if (!damage) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Damage</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">No damage data available</p>
        </CardContent>
      </Card>
    );
  }

  const scratches = damage.scratches?.count || 0;
  const dents = damage.dents?.count || 0;
  const rust = damage.rust?.count || 0;
  const cracks = damage.cracks?.count || 0;
  const paintDamage = damage.paint_damage?.count || 0;
  const wheelDamage = damage.wheel_damage?.count || 0;
  const brokenLights = damage.broken_lights?.count || 0;
  const missingParts = damage.missing_parts?.count || 0;
  const panelMisalignment = damage.panel_misalignment?.count || 0;
  const total =
    scratches +
    dents +
    rust +
    cracks +
    paintDamage +
    wheelDamage +
    brokenLights +
    missingParts +
    panelMisalignment;
  const severity = (damage.severity || "low").toLowerCase();
  const totalCost = damage.total_estimated_repair_cost ?? null;

  return (
    <Card className="md:col-span-2">
      <CardHeader className="flex-row items-start justify-between gap-3">
        <div>
          <CardTitle>Damage</CardTitle>
          {totalCost && (
            <p className="mt-1 text-sm text-muted-foreground">
              Estimated repair: <span className="font-medium text-foreground">{formatRange(totalCost)}</span>
              {totalCost.has_unknowns && (
                <span className="ml-2 text-xs">(some items un-priced)</span>
              )}
            </p>
          )}
        </div>
        <Badge variant="outline" className={cn(SEVERITY_STYLES[severity] || SEVERITY_STYLES.low)}>
          {severity.toUpperCase()}
        </Badge>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          <Stat label="Scratches" value={scratches} />
          <Stat label="Dents" value={dents} />
          <Stat label="Rust" value={rust} />
          <Stat label="Cracks" value={cracks} />
          <Stat label="Paint" value={paintDamage} />
          <Stat label="Wheels" value={wheelDamage} />
          <Stat label="Lights" value={brokenLights} />
          <Stat label="Missing" value={missingParts} />
          <Stat label="Alignment" value={panelMisalignment} />
        </div>

        <p className="text-sm text-muted-foreground">
          {total === 0
            ? "No significant damage detected."
            : `${total} damage area${total > 1 ? "s" : ""} detected across ${partGroups.length} part${partGroups.length === 1 ? "" : "s"}.`}
        </p>

        {allLocations.length > 0 && (
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border bg-secondary/30 px-3 py-2">
            <span className="text-xs text-muted-foreground">
              Showing {filteredLocations.length} of {allLocations.length} detections
            </span>
            <label className="flex items-center gap-2 text-xs text-muted-foreground">
              <span>Min confidence</span>
              <input
                type="range"
                min={0}
                max={0.95}
                step={0.05}
                value={minConfidence}
                onChange={(e) => setMinConfidence(Number(e.target.value))}
                className="h-1 w-32 accent-primary"
                aria-label="Minimum damage confidence threshold"
              />
              <span className="w-8 text-right font-mono text-foreground">
                {Math.round(minConfidence * 100)}%
              </span>
            </label>
          </div>
        )}

        {partGroups.length > 0 ? (
          <div className="space-y-2">
            {partGroups.map((group) => {
              const isOpen = expandedPart === group.part;
              return (
                <div key={group.part} className="rounded-lg border">
                  <button
                    type="button"
                    className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left hover:bg-accent/40"
                    onClick={() => setExpandedPart(isOpen ? null : group.part)}
                    aria-expanded={isOpen}
                  >
                    <div className="flex min-w-0 items-center gap-3">
                      {isOpen ? (
                        <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
                      ) : (
                        <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
                      )}
                      <div className="min-w-0">
                        <div className="truncate text-sm font-medium capitalize">
                          {group.partLabel}
                        </div>
                        <div className="text-xs text-muted-foreground">
                          {group.locations.length} detection{group.locations.length === 1 ? "" : "s"}
                          {" · "}
                          {Array.from(new Set(group.locations.map((l) => l.type || "damage"))).join(", ")}
                        </div>
                      </div>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      <Badge
                        variant="outline"
                        className={cn("text-[10px]", SEVERITY_STYLES[group.maxSeverity] || SEVERITY_STYLES.low)}
                      >
                        {group.maxSeverity.toUpperCase()}
                      </Badge>
                      {group.hasCost && (
                        <span className="hidden text-sm font-medium tabular-nums sm:inline">
                          {formatRange({
                            low: group.totalLow,
                            high: group.totalHigh,
                            midpoint: (group.totalLow + group.totalHigh) / 2,
                            currency: group.currency,
                          })}
                        </span>
                      )}
                    </div>
                  </button>
                  {isOpen && (
                    <div className="border-t bg-secondary/20 p-4">
                      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                        {group.locations.map((loc, i) => {
                          // Prefer the cropped damage snapshot; fall back to the
                          // full frame so VLM findings without a crop still show.
                          const imageSrc = loc.snapshot || loc.frame;
                          if (!imageSrc) return null;
                          const pct = Math.round((loc.confidence || 0) * 100);
                          const type = loc.type || "damage";
                          const originalIndex = (loc as DamageLocation & { __originalIndex?: number })
                            .__originalIndex;
                          const fb = originalIndex !== undefined ? feedbackByIndex[originalIndex] : undefined;
                          const isConfirmed = fb?.verdict === "confirmed";
                          const isWrong =
                            fb?.verdict === "false_positive" ||
                            fb?.verdict === "wrong_type" ||
                            fb?.verdict === "missed_severity";
                          return (
                            <div
                              key={`${imageSrc}-${i}`}
                              className="space-y-2"
                            >
                              <div className="relative aspect-square overflow-hidden rounded-lg border border-border">
                                <Image
                                  src={snapshotSrc(imageSrc)}
                                  alt={`${type} on ${group.partLabel} — ${pct}% confidence`}
                                  fill
                                  loading="lazy"
                                  unoptimized
                                  className="object-cover"
                                  sizes="(max-width: 768px) 50vw, 33vw"
                                />
                                <div className="absolute right-1.5 top-1.5 rounded-md bg-background/80 px-1.5 py-0.5 text-xs font-semibold backdrop-blur-sm">
                                  {pct}%
                                </div>
                                {loc.frame && loc.bbox && (
                                  <button
                                    type="button"
                                    aria-label="View damage location on full frame"
                                    title="View on full frame"
                                    onClick={() =>
                                      setViewerLocation({ ...loc, part_label: loc.part_label || group.partLabel })
                                    }
                                    className="absolute left-1.5 top-1.5 flex h-6 w-6 items-center justify-center rounded-md bg-background/80 text-foreground backdrop-blur-sm transition hover:bg-background"
                                  >
                                    <Maximize2 className="h-3.5 w-3.5" />
                                  </button>
                                )}
                                <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/70 to-transparent px-2 py-1.5 text-xs font-medium capitalize text-white">
                                  {type}
                                </div>
                              </div>
                              {loc.rationale && (
                                <div
                                  className={cn(
                                    "flex items-start gap-1.5 rounded-md border px-2 py-1.5 text-xs",
                                    loc.rationale_likely_real === false
                                      ? "border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-900/40 dark:bg-amber-950/30 dark:text-amber-200"
                                      : "border-border bg-background text-muted-foreground",
                                  )}
                                >
                                  <Info className="mt-0.5 h-3 w-3 shrink-0" />
                                  <span>{loc.rationale}</span>
                                </div>
                              )}
                              <div className="flex items-center justify-between gap-2">
                                {loc.estimated_cost ? (
                                  <span className="text-xs text-muted-foreground">
                                    Est. {formatRange(loc.estimated_cost)}
                                  </span>
                                ) : (
                                  <span />
                                )}
                                {inspectionId && originalIndex !== undefined && (
                                  <div className="flex items-center gap-1">
                                    <button
                                      type="button"
                                      aria-label="Confirm this detection"
                                      title="Confirm"
                                      onClick={() => recordVerdict(originalIndex, "confirmed")}
                                      disabled={fb?.pending}
                                      className={cn(
                                        "flex h-7 w-7 items-center justify-center rounded-md border text-muted-foreground transition",
                                        isConfirmed && "border-emerald-500 bg-emerald-500/10 text-emerald-600",
                                        !fb && "hover:bg-accent",
                                      )}
                                    >
                                      {fb?.pending && isConfirmed ? (
                                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                      ) : isConfirmed ? (
                                        <Check className="h-3.5 w-3.5" />
                                      ) : (
                                        <ThumbsUp className="h-3.5 w-3.5" />
                                      )}
                                    </button>
                                    <button
                                      type="button"
                                      aria-label="Mark this detection wrong"
                                      title="Wrong / false positive"
                                      onClick={() => recordVerdict(originalIndex, "false_positive")}
                                      disabled={fb?.pending}
                                      className={cn(
                                        "flex h-7 w-7 items-center justify-center rounded-md border text-muted-foreground transition",
                                        isWrong && "border-destructive bg-destructive/10 text-destructive",
                                        !fb && "hover:bg-accent",
                                      )}
                                    >
                                      {fb?.pending && isWrong ? (
                                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                      ) : (
                                        <ThumbsDown className="h-3.5 w-3.5" />
                                      )}
                                    </button>
                                  </div>
                                )}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        ) : allLocations.length > 0 ? (
          <p className="text-sm text-muted-foreground">
            No detections above {Math.round(minConfidence * 100)}% confidence. Lower the
            threshold to see weaker hits.
          </p>
        ) : null}

        {viewerLocation?.frame && (
          <DamageOverlayViewer
            location={viewerLocation}
            frameSrc={snapshotSrc(viewerLocation.frame)}
            onClose={() => setViewerLocation(null)}
          />
        )}
      </CardContent>
    </Card>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border border-border bg-secondary/30 p-3 text-center">
      <div className="text-2xl font-bold">{value}</div>
      <div className="mt-0.5 text-xs text-muted-foreground">{label}</div>
    </div>
  );
}
