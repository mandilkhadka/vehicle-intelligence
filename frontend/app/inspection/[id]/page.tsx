"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import Image from "next/image";
import { BrainCircuit, Camera, Download, Gauge, Loader2 } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import VehicleInfo from "@/components/VehicleInfo";
import OdometerInfo from "@/components/OdometerInfo";
import DamageInfo from "@/components/DamageInfo";
import ExhaustInfo from "@/components/ExhaustInfo";
import {
  getInspection,
  retryInspectionVlmAnalysis,
  updateInspectionIdentity,
  updateInspectionVlmEvidence,
  BACKEND_BASE_URL,
  type PipelineAudit,
  type PipelineAuditCheck,
  type InspectionRecord,
} from "@/lib/api";
import { safeParseJsonOrValue } from "@/lib/utils/safe-json";

export default function InspectionPage() {
  const params = useParams();
  const inspectionId = params.id as string;
  const [inspection, setInspection] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!inspectionId) return;
    let cancelled = false;
    (async () => {
      try {
        const data = await getInspection(inspectionId);
        if (!cancelled) setInspection(data);
      } catch (err) {
        console.error(err);
        if (!cancelled) setError("Failed to load inspection data");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [inspectionId]);

  const downloadReport = () => {
    if (!inspection) return;
    const blob = new Blob([JSON.stringify(inspection, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `inspection-${inspectionId}.json`;
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <AppShell>
      <div className="p-4 sm:p-6 lg:p-8">
        <PageHeader
          eyebrow="Report"
          title="Inspection Results"
          description={
            <>
              ID <span className="font-mono text-foreground">{inspectionId}</span>
            </>
          }
        >
          {inspection && (
            <Button variant="outline" onClick={downloadReport} className="gap-2">
              <Download className="h-4 w-4" />
              Download JSON
            </Button>
          )}
        </PageHeader>

            {loading && (
              <div className="flex items-center gap-2 text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" /> Loading inspection…
              </div>
            )}

            {error && !loading && (
              <Card>
                <CardContent className="py-10 text-center">
                  <p className="mb-4 text-destructive">{error}</p>
                  <Link href="/" className="text-primary underline">
                    Back to dashboard
                  </Link>
                </CardContent>
              </Card>
            )}

            {!loading && !error && !inspection && (
              <Card>
                <CardContent className="py-10 text-center">
                  <p className="mb-4 text-muted-foreground">Inspection not found</p>
                  <Link href="/" className="text-primary underline">
                    Go back home
                  </Link>
                </CardContent>
              </Card>
            )}

            {!loading && !error && inspection && (
              <InspectionContent inspection={inspection} onInspectionUpdated={setInspection} />
            )}
      </div>
    </AppShell>
  );
}

function auditValue(value: unknown): string | null {
  if (value == null || value === "") return null;
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (Array.isArray(value)) return value.map((item) => auditValue(item)).filter(Boolean).join(", ");
  return JSON.stringify(value);
}

function yesNo(value: unknown): string {
  return value ? "yes" : "no";
}

function hasVehicleIdentityEvidence(evidence: Record<string, any>): boolean {
  return [
    "brand",
    "model",
    "year",
    "variant",
    "type",
    "vehicle_category",
    "category",
    "year_range",
    "identity_source",
    "identity_override_fields",
    "vin_supplied",
    "registration_supplied",
  ].some((key) => Object.prototype.hasOwnProperty.call(evidence, key));
}

function vehicleIdentityEvidenceText(evidence: Record<string, any>): string | null {
  if (!hasVehicleIdentityEvidence(evidence)) return null;

  const parts: string[] = [];
  const vehicle = [
    auditValue(evidence.brand),
    auditValue(evidence.model),
    auditValue(evidence.year) || auditValue(evidence.year_range),
    auditValue(evidence.variant) || auditValue(evidence.variant_candidate),
  ].filter(Boolean);
  if (vehicle.length > 0) parts.push(`Vehicle: ${vehicle.join(" ")}.`);

  const category = auditValue(evidence.vehicle_category ?? evidence.category);
  const type = auditValue(evidence.type);
  if (type || category) {
    parts.push(`Type/category: ${[type, category].filter(Boolean).join(" / ")}.`);
  }

  if (evidence.confidence != null && evidence.threshold != null) {
    parts.push(`Confidence ${evidence.confidence} is below threshold ${evidence.threshold}.`);
  }

  const source = auditValue(evidence.identity_source);
  if (source) parts.push(`Source: ${source}.`);

  if (Object.prototype.hasOwnProperty.call(evidence, "identity_override_fields")) {
    const overrideFields = auditValue(evidence.identity_override_fields);
    parts.push(`Override fields: ${overrideFields || "none"}.`);
  }

  if (
    Object.prototype.hasOwnProperty.call(evidence, "vin_supplied") ||
    Object.prototype.hasOwnProperty.call(evidence, "registration_supplied")
  ) {
    parts.push(
      `Supplied evidence: VIN ${yesNo(evidence.vin_supplied)}, registration ${yesNo(evidence.registration_supplied)}.`,
    );
  }

  const missing = [];
  if (!evidence.year) missing.push("exact year");
  if (!evidence.variant) missing.push("trim/version");
  if (missing.length > 0 && !evidence.vin_supplied && !evidence.registration_supplied) {
    parts.push(`Missing ${missing.join(" and ")}; provide VIN or registration to resolve.`);
  }

  const candidates = auditValue(evidence.variant_candidates);
  if (candidates) parts.push(`Variant candidates: ${candidates}.`);

  const notes = auditValue(evidence.identity_notes);
  if (notes) parts.push(`Notes: ${notes}`);

  return parts.length > 0 ? parts.join(" ") : null;
}

function auditEvidenceText(evidence: Record<string, any>): string | null {
  const vehicleIdentityText = vehicleIdentityEvidenceText(evidence);
  if (vehicleIdentityText) return vehicleIdentityText;

  const rawReason =
    evidence.reason ||
    evidence.visual_analysis_reason ||
    evidence.identity_notes ||
    evidence.gemini_live_reason;
  if (typeof rawReason === "string") return rawReason;
  if (rawReason != null) return JSON.stringify(rawReason);

  if (evidence.temporal_coverage_ratio != null) {
    return `Temporal coverage ${evidence.temporal_coverage_ratio} (threshold ${evidence.threshold ?? "n/a"}).`;
  }
  if (Array.isArray(evidence.missing_named_views) && evidence.missing_named_views.length > 0) {
    return `Missing views: ${evidence.missing_named_views.join(", ")}.`;
  }
  if (Array.isArray(evidence.missing_paths) && evidence.missing_paths.length > 0) {
    return `Missing frame paths: ${evidence.missing_paths.join(", ")}.`;
  }
  if (Array.isArray(evidence.missing_quality) && evidence.missing_quality.length > 0) {
    return `Missing quality scores: ${evidence.missing_quality.join(", ")}.`;
  }
  if (Array.isArray(evidence.low_quality) && evidence.low_quality.length > 0) {
    return `Low-quality selections: ${evidence.low_quality
      .map((item: any) => `${item.view || "frame"}=${item.quality_score}`)
      .join(", ")}.`;
  }
  if (Array.isArray(evidence.missing_categories) && evidence.missing_categories.length > 0) {
    return `Missing damage categories: ${evidence.missing_categories.join(", ")}.`;
  }
  if (evidence.concrete_part_category_count != null && evidence.threshold != null) {
    return `Modification part coverage ${evidence.concrete_part_category_count} (threshold ${evidence.threshold}).`;
  }
  if (evidence.confidence != null && evidence.threshold != null) {
    return `Confidence ${evidence.confidence} is below threshold ${evidence.threshold}.`;
  }

  return null;
}

function InspectionContent({
  inspection,
  onInspectionUpdated,
}: {
  inspection: any;
  onInspectionUpdated: (inspection: InspectionRecord) => void;
}) {
  const parseMaybe = <T,>(v: string | T | null | undefined, fallback: T) =>
    safeParseJsonOrValue<T>(v, fallback);

  const odometerInfo = parseMaybe<Record<string, any> | null>(inspection.odometer_info, null);
  const odometer = {
    ...(odometerInfo || {}),
    value: odometerInfo?.value ?? inspection.odometer_value,
    confidence: odometerInfo?.confidence ?? inspection.odometer_confidence,
    speedometer_image_path: odometerInfo?.speedometer_image_path ?? inspection.speedometer_image_path,
  };

  const damage =
    parseMaybe(inspection.damage_summary, null) || {
      scratches: { count: inspection.scratches_detected || 0 },
      dents: { count: inspection.dents_detected || 0 },
      rust: { count: inspection.rust_detected || 0 },
      severity: inspection.damage_severity || "low",
    };

  const exhaust = {
    type: inspection.exhaust_type,
    confidence: inspection.exhaust_confidence,
    exhaust_image_path: inspection.exhaust_image_path,
  };

  const report = parseMaybe<Record<string, any> | null>(inspection.inspection_report, null);
  const reportVehicle = report?.vehicle_details || report?.gemini_analysis?.vehicle || {};
  const parsedVehicleInfo = parseMaybe<Record<string, any> | null>(inspection.vehicle_info, null);
  const vehicleInfo = parsedVehicleInfo
    ? {
        ...parsedVehicleInfo,
        vehicle_category: parsedVehicleInfo.vehicle_category ?? reportVehicle.vehicle_category,
        year_range: parsedVehicleInfo.year_range ?? reportVehicle.year_range,
        generation: parsedVehicleInfo.generation ?? reportVehicle.generation,
        variant_candidates:
          parsedVehicleInfo.variant_candidates ?? reportVehicle.variant_candidates,
        variant_candidate: parsedVehicleInfo.variant_candidate ?? reportVehicle.variant_candidate,
        variant_confidence: parsedVehicleInfo.variant_confidence ?? reportVehicle.variant_confidence,
        variant_candidates_ranked:
          parsedVehicleInfo.variant_candidates_ranked ?? reportVehicle.variant_candidates_ranked,
        model_confidence: parsedVehicleInfo.model_confidence ?? reportVehicle.model_confidence,
        model_candidates: parsedVehicleInfo.model_candidates ?? reportVehicle.model_candidates,
        identity_source: parsedVehicleInfo.identity_source ?? reportVehicle.identity_source,
        identity_override_fields:
          parsedVehicleInfo.identity_override_fields ?? reportVehicle.identity_override_fields,
        vin: parsedVehicleInfo.vin ?? reportVehicle.vin,
        registration: parsedVehicleInfo.registration ?? reportVehicle.registration,
        identity_notes: parsedVehicleInfo.identity_notes ?? reportVehicle.identity_notes,
      }
    : {
        type: inspection.vehicle_type || reportVehicle.type,
        brand: inspection.vehicle_brand || reportVehicle.brand,
        model: inspection.vehicle_model || reportVehicle.model,
        year: inspection.vehicle_year || reportVehicle.year,
        variant: inspection.vehicle_variant || reportVehicle.variant,
        vehicle_category: reportVehicle.vehicle_category,
        year_range: reportVehicle.year_range,
        generation: reportVehicle.generation,
        variant_candidates: reportVehicle.variant_candidates,
        variant_candidate: reportVehicle.variant_candidate,
        variant_confidence: reportVehicle.variant_confidence,
        variant_candidates_ranked: reportVehicle.variant_candidates_ranked,
        model_confidence: reportVehicle.model_confidence,
        model_candidates: reportVehicle.model_candidates,
        identity_source: reportVehicle.identity_source,
        identity_override_fields: reportVehicle.identity_override_fields,
        vin: reportVehicle.vin,
        registration: reportVehicle.registration,
        identity_notes: reportVehicle.identity_notes,
        color: reportVehicle.color,
        confidence: inspection.vehicle_confidence ?? reportVehicle.confidence,
      };
  const frames = parseMaybe<string[]>(inspection.extracted_frames, []);
  const gemini = report?.gemini_analysis;
  const visualProvider =
    gemini?.provider === "openai"
      ? "OpenAI Vision"
      : gemini?.provider === "gemini" || gemini?.available
        ? "Gemini Vision"
        : "VLM";
  const visualAnalysis =
    report?.visual_analysis ||
    (gemini && typeof gemini.available === "boolean"
      ? { available: gemini.available, reason: gemini.reason }
      : null);
  const frameAnalysis = report?.frame_analysis;
  const reportModification = report?.modification_assessment;
  const pipelineAudit = report?.pipeline_audit as PipelineAudit | undefined;
  const [retryingVlm, setRetryingVlm] = useState(false);
  const [vlmRetryError, setVlmRetryError] = useState<string | null>(null);
  const failedAuditChecks = Array.isArray(pipelineAudit?.checks)
    ? pipelineAudit.checks.filter((check: PipelineAuditCheck) => !check?.passed)
    : [];
  const vehicleIdentityFailed = failedAuditChecks.some(
    (check: PipelineAuditCheck) => check?.id === "vehicle_identity",
  );
  const referenceImage = report?.reference_image || gemini?.reference_image;
  const orderedViews = [
    "front",
    "front-left",
    "left",
    "rear-left",
    "rear",
    "rear-right",
    "right",
    "front-right",
    "interior",
    "dashboard",
  ];
  const organizedShots = orderedViews
    .map((view) => {
      const shot = frameAnalysis?.angle_shots?.[view];
      return shot ? { view, ...shot } : null;
    })
    .filter(Boolean);
  const dashboardCandidates = Array.isArray(frameAnalysis?.dashboard_candidates)
    ? frameAnalysis.dashboard_candidates.slice(0, 3)
    : [];

  const retryVlm = async () => {
    setRetryingVlm(true);
    setVlmRetryError(null);
    try {
      const updated = await retryInspectionVlmAnalysis(inspection.id);
      onInspectionUpdated(updated);
    } catch (error: any) {
      setVlmRetryError(
        error?.response?.data?.message ||
          error?.message ||
          "Failed to retry VLM analysis",
      );
    } finally {
      setRetryingVlm(false);
    }
  };

  return (
    <div className="space-y-6">
      {report && (report.summary || report.recommendations?.length || reportModification?.summary) && (
        <Card>
          <CardHeader>
            <CardTitle>Summary</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {report.summary && (
              <p className="text-sm leading-relaxed text-foreground">{report.summary}</p>
            )}
            {reportModification?.summary && (
              <div>
                <h4 className="mb-2 text-sm font-semibold">Modification assessment</h4>
                <p className="text-sm text-muted-foreground">{reportModification.summary}</p>
                {Array.isArray(reportModification.items) && reportModification.items.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {reportModification.items.slice(0, 8).map((item: any, i: number) => (
                      <Badge
                        key={`${item.part}-${i}`}
                        variant={item.status === "modified" ? "secondary" : "outline"}
                        className="rounded-md capitalize"
                      >
                        {String(item.part || "part").replace("_", " ")}: {item.status || "unknown"}
                      </Badge>
                    ))}
                  </div>
                )}
              </div>
            )}
            {report.recommendations?.length > 0 && (
              <div>
                <h4 className="mb-2 text-sm font-semibold">Recommendations</h4>
                <ul className="list-inside list-disc space-y-1 text-sm text-muted-foreground">
                  {report.recommendations.map((rec: string, i: number) => (
                    <li key={i}>{rec}</li>
                  ))}
                </ul>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {pipelineAudit && (
        <Card className="overflow-hidden">
          <CardHeader className="border-b border-border bg-secondary/30">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <CardTitle>Pipeline Verification</CardTitle>
              <Badge
                variant={pipelineAudit.status === "complete" ? "secondary" : "outline"}
                className="w-fit rounded-md bg-background font-mono text-[11px] uppercase tracking-normal"
              >
                {pipelineAudit.status || "unknown"}
              </Badge>
            </div>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            {failedAuditChecks.length > 0 ? (
              <div className="grid gap-2">
                {failedAuditChecks.map((check: PipelineAuditCheck) => {
                  const evidence = check.evidence || {};
                  const reason = auditEvidenceText(evidence);
                  return (
                    <div
                      key={check.id}
                      className="rounded-lg border border-border bg-background/50 p-3"
                    >
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge variant="outline" className="rounded-md">
                          {String(check.id || "check").replaceAll("_", " ")}
                        </Badge>
                        <span className="font-medium">{check.requirement}</span>
                      </div>
                      {reason && (
                        <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
                          {reason}
                        </p>
                      )}
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="text-muted-foreground">All runtime verification checks passed.</p>
            )}
          </CardContent>
        </Card>
      )}

      {vehicleIdentityFailed && (
        <IdentityEvidenceForm
          inspectionId={inspection.id}
          initialVehicleInfo={vehicleInfo}
          onUpdated={onInspectionUpdated}
        />
      )}

      {(organizedShots.length > 0 || dashboardCandidates.length > 0) && (
        <Card className="overflow-hidden">
          <CardHeader className="border-b border-border bg-secondary/30">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <CardTitle className="flex items-center gap-2">
                <Camera className="h-5 w-5 text-primary" />
                Organized Vehicle Shots
              </CardTitle>
              {frameAnalysis?.coverage && (
                <div className="flex flex-wrap gap-2">
                  <Badge variant="outline" className="w-fit rounded-md bg-background font-mono text-[11px] uppercase tracking-normal">
                    {Math.round((frameAnalysis.coverage.ratio || 0) * 100)}% selected
                  </Badge>
                  {typeof frameAnalysis.coverage.high_confidence_ratio === "number" && (
                    <Badge variant="outline" className="w-fit rounded-md bg-background font-mono text-[11px] uppercase tracking-normal">
                      {Math.round((frameAnalysis.coverage.high_confidence_ratio || 0) * 100)}% high confidence
                    </Badge>
                  )}
                </div>
              )}
            </div>
          </CardHeader>
          <CardContent className="space-y-5">
            {organizedShots.length > 0 && (
              <div>
                <div className="mb-3 flex items-center justify-between gap-3">
                  <h4 className="text-sm font-semibold">Angle shots</h4>
                  {typeof frameAnalysis?.frames_analyzed === "number" && (
                    <span className="text-xs text-muted-foreground">
                      {frameAnalysis.frames_analyzed} frames analyzed
                    </span>
                  )}
                </div>
                <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
                  {organizedShots.map((shot: any) => {
                    const path = uploadPath(shot.organized_path || shot.frame);
                    if (!path) return null;
                    return (
                      <div key={shot.view} className="overflow-hidden rounded-lg border border-border bg-background">
                        <div className="relative aspect-video">
                          <Image
                            src={`${BACKEND_BASE_URL}/${path}`}
                            alt={`${shot.view} angle`}
                            fill
                            className="object-cover"
                            unoptimized
                          />
                        </div>
                        <div className="flex items-center justify-between gap-2 px-2 py-1.5 text-xs">
                          <span className="truncate font-medium capitalize">{String(shot.view).replace("-", " ")}</span>
                          {typeof shot.score === "number" && (
                            <span className="font-mono text-muted-foreground">{Math.round(shot.score * 100)}%</span>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {dashboardCandidates.length > 0 && (
              <div>
                <h4 className="mb-3 flex items-center gap-2 text-sm font-semibold">
                  <Gauge className="h-4 w-4 text-primary" />
                  Dashboard candidates
                </h4>
                <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                  {dashboardCandidates.map((candidate: any, i: number) => {
                    const path = uploadPath(candidate.crop_path || candidate.organized_path || candidate.frame);
                    if (!path) return null;
                    return (
                      <div key={`${candidate.frame_index ?? i}-${path}`} className="overflow-hidden rounded-lg border border-border bg-background">
                        <div className="relative aspect-video">
                          <Image
                            src={`${BACKEND_BASE_URL}/${path}`}
                            alt={`Dashboard candidate ${i + 1}`}
                            fill
                            className="object-cover"
                            unoptimized
                          />
                        </div>
                        <div className="flex items-center justify-between gap-2 px-2 py-1.5 text-xs">
                          <span className="font-medium">Candidate {i + 1}</span>
                          {typeof candidate.score === "number" && (
                            <span className="font-mono text-muted-foreground">{Math.round(candidate.score * 100)}%</span>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {gemini?.available && (
        <Card className="overflow-hidden">
          <CardHeader className="border-b border-border bg-secondary/30">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <CardTitle className="flex items-center gap-2">
                <BrainCircuit className="h-5 w-5 text-primary" />
                AI Visual Analysis
              </CardTitle>
              <Badge variant="outline" className="w-fit rounded-md bg-background font-mono text-[11px] uppercase tracking-normal">
                {visualProvider}
              </Badge>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            {gemini.summary && (
              <p className="text-sm leading-relaxed text-foreground">{gemini.summary}</p>
            )}
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2 text-sm">
              {gemini.vehicle?.brand && (
                <div>
                  <span className="font-semibold">Identified vehicle: </span>
                  {[gemini.vehicle.brand, gemini.vehicle.model, gemini.vehicle.year]
                    .filter(Boolean)
                    .join(" ")}
                  {gemini.vehicle.variant ? ` (${gemini.vehicle.variant})` : ""}
                </div>
              )}
              {gemini.vehicle?.color && (
                <div>
                  <span className="font-semibold">Color: </span>
                  {gemini.vehicle.color}
                </div>
              )}
              {gemini.overall_condition && (
                <div>
                  <span className="font-semibold">Overall condition: </span>
                  {gemini.overall_condition}
                </div>
              )}
              {typeof gemini.vehicle?.confidence === "number" && (
                <div>
                  <span className="font-semibold">Visual ID confidence: </span>
                  {(gemini.vehicle.confidence * 100).toFixed(0)}%
                </div>
              )}
            </div>
            {gemini.damage_findings && (
              <div>
                <h4 className="mb-1 text-sm font-semibold">Damage findings</h4>
                <p className="text-sm text-muted-foreground">{gemini.damage_findings}</p>
              </div>
            )}
            {Array.isArray(gemini.damage_items) && gemini.damage_items.length > 0 && (
              <div>
                <h4 className="mb-2 text-sm font-semibold">Visible damage items</h4>
                <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
                  {gemini.damage_items.slice(0, 8).map((item: any, i: number) => (
                    <div key={`${item.type}-${item.location}-${i}`} className="rounded-lg border border-border bg-background/50 p-3 text-xs">
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge variant="outline" className="rounded-md capitalize">{String(item.type || "damage").replace("_", " ")}</Badge>
                        <span className="font-medium text-foreground">{item.location || "Unknown location"}</span>
                        {item.severity && <span className="text-muted-foreground">· {item.severity}</span>}
                      </div>
                      {item.notes && <p className="mt-2 text-muted-foreground">{item.notes}</p>}
                    </div>
                  ))}
                </div>
              </div>
            )}
            {(gemini.modification_findings || (Array.isArray(gemini.modification_items) && gemini.modification_items.length > 0)) && (
              <div>
                <h4 className="mb-2 text-sm font-semibold">Modification assessment</h4>
                {gemini.modification_findings && (
                  <p className="mb-2 text-sm text-muted-foreground">{gemini.modification_findings}</p>
                )}
                {Array.isArray(gemini.modification_items) && gemini.modification_items.length > 0 && (
                  <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
                    {gemini.modification_items.slice(0, 8).map((item: any, i: number) => (
                      <div key={`${item.part}-${i}`} className="flex items-center justify-between gap-3 rounded-lg border border-border bg-background/50 px-3 py-2 text-xs">
                        <span className="font-medium capitalize">{String(item.part || "part").replace("_", " ")}</span>
                        <Badge variant={item.status === "modified" ? "secondary" : "outline"} className="rounded-md capitalize">
                          {item.status || "unknown"}
                        </Badge>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
            {Array.isArray(gemini.per_frame) && gemini.per_frame.length > 0 && (
              <div>
                <h4 className="mb-2 text-sm font-semibold">Per-frame observations</h4>
                <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                  {gemini.per_frame.map((f: any, i: number) => {
                    const path = uploadPath(f.frame);
                    return (
                      <div key={i} className="rounded-lg border border-border bg-background/50 p-3">
                        {path && (
                          <div className="relative mb-2 aspect-video overflow-hidden rounded">
                            <Image
                              src={`${BACKEND_BASE_URL}/${path}`}
                              alt={`Frame ${f.index ?? i + 1}`}
                              fill
                              className="object-cover"
                              unoptimized
                            />
                          </div>
                        )}
                        <div className="text-xs text-muted-foreground">
                          <div>
                            <span className="font-semibold text-foreground">
                              Frame {f.index ?? i + 1}
                            </span>
                            {f.view ? ` · ${f.view}` : ""}
                            {f.condition ? ` · ${f.condition}` : ""}
                          </div>
                          {f.observations && <p className="mt-1">{f.observations}</p>}
                          {f.damage_notes && (
                            <p className="mt-1">
                              <span className="font-semibold">Damage: </span>
                              {f.damage_notes}
                            </p>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {visualAnalysis && !visualAnalysis.available && (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(340px,0.8fr)]">
          <Card className="overflow-hidden">
            <CardHeader className="border-b border-border bg-secondary/30">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <CardTitle className="flex items-center gap-2">
                  <BrainCircuit className="h-5 w-5 text-muted-foreground" />
                  AI Visual Analysis Unavailable
                </CardTitle>
                <Badge variant="outline" className="w-fit rounded-md bg-background font-mono text-[11px] uppercase tracking-normal">
                  Manual review
                </Badge>
              </div>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <p className="text-foreground">
                Final visual conclusions were not verified by the Gemini/VLM pass.
              </p>
              {visualAnalysis.reason && (
                <p className="text-muted-foreground">{visualAnalysis.reason}</p>
              )}
              {vlmRetryError && <p className="text-destructive">{vlmRetryError}</p>}
              <Button
                type="button"
                variant="outline"
                className="mt-2 gap-2"
                onClick={retryVlm}
                disabled={retryingVlm}
              >
                {retryingVlm && <Loader2 className="h-4 w-4 animate-spin" />}
                {retryingVlm ? "Retrying VLM..." : "Retry VLM Analysis"}
              </Button>
            </CardContent>
          </Card>
          <VlmEvidenceImport inspectionId={inspection.id} onUpdated={onInspectionUpdated} />
        </div>
      )}

      {referenceImage?.search_url && (
        <Card>
          <CardHeader>
            <CardTitle>Brand-new reference (same model)</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            {referenceImage.description && (
              <p className="text-muted-foreground">{referenceImage.description}</p>
            )}
            <a
              href={referenceImage.search_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center text-primary underline"
            >
              View official press images on Google
            </a>
            {referenceImage.search_query && (
              <p className="text-xs text-muted-foreground">
                Search query: <code>{referenceImage.search_query}</code>
              </p>
            )}
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        <VehicleInfo vehicleInfo={vehicleInfo} />
        <OdometerInfo odometer={odometer} />
        <DamageInfo damage={damage} />
        <ExhaustInfo exhaust={exhaust} />
      </div>

      {frames.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Extracted Frames</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              {frames
                .filter((f) => typeof f === "string" && f && !f.startsWith("frames/sample/"))
                .slice(0, 12)
                .map((frame, i) => {
                  const path = uploadPath(frame);
                  if (!path) return null;
                  return (
                    <div
                      key={i}
                      className="relative aspect-video overflow-hidden rounded-lg border border-border"
                    >
                      <Image
                        src={`${BACKEND_BASE_URL}/${path}`}
                        alt={`Frame ${i + 1}`}
                        fill
                        className="object-cover"
                        unoptimized
                      />
                    </div>
                  );
                })}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function VlmEvidenceImport({
  inspectionId,
  onUpdated,
}: {
  inspectionId: string;
  onUpdated: (inspection: InspectionRecord) => void;
}) {
  const [jsonText, setJsonText] = useState("");
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const hasJson = jsonText.trim().length > 0;

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!hasJson) return;
    setSaving(true);
    setFormError(null);
    try {
      const parsed = JSON.parse(jsonText);
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        throw new Error("VLM evidence must be a JSON object");
      }
      const updated = await updateInspectionVlmEvidence(inspectionId, parsed);
      setJsonText("");
      onUpdated(updated);
    } catch (error: any) {
      setFormError(
        error?.response?.data?.message ||
          error?.message ||
          "Failed to save VLM evidence",
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>External VLM Evidence</CardTitle>
      </CardHeader>
      <CardContent>
        <form className="space-y-3" onSubmit={submit}>
          <div className="space-y-2">
            <Label htmlFor="vlm_evidence_json">VLM result JSON</Label>
            <textarea
              id="vlm_evidence_json"
              value={jsonText}
              onChange={(event) => setJsonText(event.target.value)}
              rows={8}
              className="min-h-40 w-full resize-y rounded-md border border-input bg-background px-3 py-2 font-mono text-xs text-foreground shadow-sm outline-none transition-colors placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring"
              placeholder='{"available":true,"provider":"external","vehicle":{"brand":"Toyota","model":"Sienta","year":"2024","variant":"Hybrid Z","type":"car","vehicle_category":"compact minivan","confidence":0.9}}'
            />
          </div>
          {formError && <p className="text-sm text-destructive">{formError}</p>}
          <Button type="submit" disabled={!hasJson || saving}>
            {saving ? "Saving..." : "Save VLM Evidence"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

function IdentityEvidenceForm({
  inspectionId,
  initialVehicleInfo,
  onUpdated,
}: {
  inspectionId: string;
  initialVehicleInfo: Record<string, any>;
  onUpdated: (inspection: InspectionRecord) => void;
}) {
  const [form, setForm] = useState({
    vehicle_brand: "",
    vehicle_model: "",
    vehicle_year: "",
    vehicle_variant: "",
    vehicle_type: "",
    vehicle_category: "",
    vin: "",
    registration: "",
  });
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const updateField = (field: keyof typeof form, value: string) => {
    setForm((current) => ({ ...current, [field]: value }));
  };

  const hasEvidence = Object.values(form).some((value) => String(value).trim());

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!hasEvidence) return;
    setSaving(true);
    setFormError(null);
    try {
      const updated = await updateInspectionIdentity(inspectionId, {
        vehicle_identity_source: "manual_review",
        ...form,
      });
      onUpdated(updated);
    } catch (error: any) {
      setFormError(
        error?.response?.data?.message ||
          error?.message ||
          "Failed to save identity evidence",
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Verified Identity Evidence</CardTitle>
      </CardHeader>
      <CardContent>
        <form className="space-y-4" onSubmit={submit}>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <IdentityField
              id="identity_vehicle_brand"
              label="Make"
              value={form.vehicle_brand}
              placeholder={initialVehicleInfo.brand}
              onChange={(value) => updateField("vehicle_brand", value)}
            />
            <IdentityField
              id="identity_vehicle_model"
              label="Model"
              value={form.vehicle_model}
              placeholder={initialVehicleInfo.model}
              onChange={(value) => updateField("vehicle_model", value)}
            />
            <IdentityField
              id="identity_vehicle_year"
              label="Year"
              value={form.vehicle_year}
              placeholder={initialVehicleInfo.year}
              onChange={(value) => updateField("vehicle_year", value)}
            />
            <IdentityField
              id="identity_vehicle_variant"
              label="Trim / variant"
              value={form.vehicle_variant}
              placeholder={initialVehicleInfo.variant}
              onChange={(value) => updateField("vehicle_variant", value)}
            />
            <IdentityField
              id="identity_vehicle_type"
              label="Vehicle type"
              value={form.vehicle_type}
              placeholder={initialVehicleInfo.type}
              onChange={(value) => updateField("vehicle_type", value)}
            />
            <IdentityField
              id="identity_vehicle_category"
              label="Category"
              value={form.vehicle_category}
              placeholder={initialVehicleInfo.vehicle_category || initialVehicleInfo.category}
              onChange={(value) => updateField("vehicle_category", value)}
            />
            <IdentityField
              id="identity_vin"
              label="VIN / chassis"
              value={form.vin}
              placeholder={initialVehicleInfo.vin}
              onChange={(value) => updateField("vin", value)}
            />
            <IdentityField
              id="identity_registration"
              label="Registration"
              value={form.registration}
              placeholder={initialVehicleInfo.registration}
              onChange={(value) => updateField("registration", value)}
            />
          </div>
          {formError && <p className="text-sm text-destructive">{formError}</p>}
          <Button type="submit" disabled={!hasEvidence || saving}>
            {saving ? "Saving..." : "Save Evidence"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

function IdentityField({
  id,
  label,
  value,
  placeholder,
  onChange,
}: {
  id: string;
  label: string;
  value: string;
  placeholder?: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="space-y-2">
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        value={value}
        placeholder={placeholder || undefined}
        onChange={(event) => onChange(event.target.value)}
      />
    </div>
  );
}

function uploadPath(path: unknown): string | null {
  if (typeof path !== "string" || !path) return null;
  return path.startsWith("uploads/") ? path : `uploads/${path.replace(/^.*uploads\//, "")}`;
}
