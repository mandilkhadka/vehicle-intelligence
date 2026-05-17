"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import Image from "next/image";
import {
  BrainCircuit,
  Camera,
  ChevronLeft,
  ChevronRight,
  Download,
  FileText,
  Gauge,
  Loader2,
  Maximize2,
  Minimize2,
  RotateCcw,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
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

type ReviewShot = {
  id: string;
  view: string;
  group: "angle" | "dashboard" | "section";
  imagePath: string;
  previewPath: string;
  score?: number;
  qualityScore?: number;
  timestampSeconds?: number;
};

type DamageLocation = {
  id: string;
  type: string;
  frame?: string;
  snapshot?: string;
  confidence?: number;
  severity?: string;
  bbox?: [number, number, number, number];
  angle?: string;
  linkedView?: string;
};

type AiListingBuilderContent = {
  title: string;
  shortSummary: string;
  conditionGrade: string;
  detectedDamageList: string[];
  recommendedDisclosures: string[];
  missingPhotoChecklist: string[];
  confidenceWarnings: string[];
  buyerFacingReport: string;
};

const EXTERIOR_360_ORDER = [
  "front",
  "front-left",
  "left",
  "rear-left",
  "rear",
  "rear-right",
  "right",
  "front-right",
];

const DETAIL_360_ORDER = [
  "dashboard",
  "steering-wheel",
  "odometer",
  "infotainment",
  "seats",
  "trunk",
  "engine-bay",
  "wheels",
  "tyres",
  "exhaust",
  "damage-closeups",
];

const REVIEW_VIEW_ORDER = [
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
  "steering-wheel",
  "odometer",
  "infotainment",
  "seats",
  "wheels",
  "tyres",
  "exhaust",
  "trunk",
  "engine-bay",
  "damage-closeups",
];

function displayViewName(view: string): string {
  return String(view || "frame").replaceAll("-", " ");
}

function buildReviewShots(frameAnalysis: any, inspectionAnalysis?: any): ReviewShot[] {
  const shots: ReviewShot[] = [];
  const seen = new Set<string>();
  const seenPaths = new Set<string>();
  const addShot = (view: string, source: any, group: ReviewShot["group"], index = 0) => {
    if (!source || typeof source !== "object") return;
    const imagePath = source.inspection_path || source.organized_path || source.frame;
    const pathKey = uploadKey(imagePath);
    if (!imagePath || seen.has(`${group}:${view}:${imagePath}`) || (pathKey && seenPaths.has(pathKey))) return;
    seen.add(`${group}:${view}:${imagePath}`);
    if (pathKey) seenPaths.add(pathKey);
    shots.push({
      id: `${group}-${view}-${index}`,
      view,
      group,
      imagePath,
      previewPath: source.preview_path || source.inspection_path || source.organized_path || source.frame,
      score:
        typeof source.confidence === "number"
          ? source.confidence
          : typeof source.score === "number"
            ? source.score
            : undefined,
      qualityScore: typeof source.quality_score === "number" ? source.quality_score : undefined,
      timestampSeconds:
        typeof source.timestamp_seconds === "number" ? source.timestamp_seconds : undefined,
    });
  };

  const routedSections = inspectionAnalysis?.sections;
  if (routedSections && typeof routedSections === "object") {
    const order = Array.isArray(inspectionAnalysis?.section_order)
      ? inspectionAnalysis.section_order
      : [...EXTERIOR_360_ORDER, ...DETAIL_360_ORDER];
    order.forEach((view: string) => {
      [...(routedSections[view] || [])]
        .sort((a: any, b: any) => {
          const confidenceDelta = Number(b?.confidence || 0) - Number(a?.confidence || 0);
          if (confidenceDelta !== 0) return confidenceDelta;
          const qualityDelta = Number(b?.quality_score || 0) - Number(a?.quality_score || 0);
          if (qualityDelta !== 0) return qualityDelta;
          return Number(a?.timestamp_seconds ?? Number.MAX_SAFE_INTEGER)
            - Number(b?.timestamp_seconds ?? Number.MAX_SAFE_INTEGER);
        })
        .forEach((source: any, index: number) => {
          addShot(source?.section || view, source, "section", index);
        });
    });
  }

  const angleShots = frameAnalysis?.angle_shots || {};
  REVIEW_VIEW_ORDER.forEach((view) => addShot(view, angleShots[view], "angle"));
  (frameAnalysis?.dashboard_candidates || []).slice(0, 6).forEach((candidate: any, index: number) => {
    addShot(candidate?.view || "dashboard", candidate, "dashboard", index);
  });

  return shots;
}

function normalizeDamageLocations(damage: any): DamageLocation[] {
  const locations = Array.isArray(damage?.locations) ? damage.locations : [];
  return locations
    .map((location: any, index: number) => {
      if (!location || typeof location !== "object") return null;
      const bbox = Array.isArray(location.bbox) && location.bbox.length === 4
        ? location.bbox.map((value: unknown) => Number(value)) as [number, number, number, number]
        : undefined;
      return {
        id: `${location.type || "damage"}-${index}`,
        type: String(location.type || "damage"),
        frame: typeof location.frame === "string" ? location.frame : undefined,
        snapshot: typeof location.snapshot === "string" ? location.snapshot : undefined,
        confidence: typeof location.confidence === "number" ? location.confidence : undefined,
        severity:
          typeof location.severity === "string"
            ? location.severity
            : typeof location.confidence === "number" && location.confidence >= 0.75
              ? "high"
              : typeof location.confidence === "number" && location.confidence >= 0.45
                ? "medium"
                : undefined,
        bbox,
        angle: typeof location.angle === "string" ? location.angle : undefined,
        linkedView: typeof location.linked_view === "string" ? location.linked_view : undefined,
      };
    })
    .filter(Boolean) as DamageLocation[];
}

function uploadKey(path: unknown): string | null {
  const normalized = uploadPath(path);
  if (!normalized) return null;
  return normalized.replace(/^uploads\//, "");
}

function damageMatchesShot(location: DamageLocation, shot: ReviewShot): boolean {
  const linkedView = location.linkedView || location.angle;
  if (linkedView && linkedView === shot.view) return true;

  const locationFrame = uploadKey(location.frame);
  if (!locationFrame) return false;
  return [shot.imagePath, shot.previewPath].some((path) => uploadKey(path) === locationFrame);
}

function orderedShots(shots: ReviewShot[], order: string[]): ReviewShot[] {
  const byView = new Map<string, ReviewShot>();
  shots.forEach((shot) => {
    if (!byView.has(shot.view)) byView.set(shot.view, shot);
  });
  return order.map((view) => byView.get(view)).filter(Boolean) as ReviewShot[];
}

function cleanText(value: unknown): string {
  if (value == null) return "";
  return String(value).replace(/\s+/g, " ").trim();
}

function displayValue(value: unknown): string {
  return cleanText(value) || "Not supplied";
}

function formatPercent(value: unknown): string | null {
  if (typeof value !== "number" || Number.isNaN(value)) return null;
  return `${Math.round(value * 100)}%`;
}

function uniqueList(items: Array<string | null | undefined>): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  items.forEach((item) => {
    const value = cleanText(item);
    if (!value) return;
    const key = value.toLowerCase();
    if (seen.has(key)) return;
    seen.add(key);
    out.push(value);
  });
  return out;
}

function normalizeLabel(value: unknown): string {
  return cleanText(value).replaceAll("_", " ").replaceAll("-", " ");
}

function buildDamageItems(damage: any, gemini: any, inspectionAnalysis: any): string[] {
  const items: string[] = [];
  const sources = [
    ...(Array.isArray(damage?.locations) ? damage.locations : []),
    ...(Array.isArray(gemini?.damage_items) ? gemini.damage_items : []),
    ...(Array.isArray(inspectionAnalysis?.damage_detections) ? inspectionAnalysis.damage_detections : []),
  ];

  sources.forEach((item: any) => {
    const type = normalizeLabel(item?.type || "damage");
    const location = cleanText(item?.location || item?.section || item?.linked_view || item?.angle);
    const severity = cleanText(item?.severity);
    const confidence = formatPercent(item?.confidence);
    items.push(
      [
        type || "damage",
        location ? `at ${location}` : "",
        severity ? `(${severity})` : "",
        confidence ? `confidence ${confidence}` : "",
      ]
        .filter(Boolean)
        .join(" "),
    );
  });

  const categoryLabels: Record<string, string> = {
    scratches: "Scratches",
    dents: "Dents",
    rust: "Rust",
    cracks: "Cracks",
    paint_damage: "Paint damage",
    wheel_damage: "Wheel damage",
    broken_lights: "Broken lights",
    missing_parts: "Missing parts",
    panel_misalignment: "Panel misalignment",
  };
  Object.entries(categoryLabels).forEach(([key, label]) => {
    const count = Number(damage?.[key]?.count || 0);
    if (count > 0) items.push(`${label}: ${count}`);
  });

  return uniqueList(items);
}

function sectionImageCount(inspectionAnalysis: any, section: string): number {
  const images = inspectionAnalysis?.sections?.[section];
  return Array.isArray(images) ? images.length : 0;
}

function buildMissingPhotoChecklist(inspectionAnalysis: any, frameAnalysis: any): string[] {
  const required = [
    ...EXTERIOR_360_ORDER,
    "dashboard",
    "odometer",
    "steering-wheel",
    "infotainment",
    "seats",
    "trunk",
    "engine-bay",
    "wheels",
    "tyres",
    "exhaust",
    "damage-closeups",
  ];
  const missing = required.filter((section) => {
    if (sectionImageCount(inspectionAnalysis, section) > 0) return false;
    if (frameAnalysis?.angle_shots?.[section]) return false;
    if (
      section === "dashboard" &&
      Array.isArray(frameAnalysis?.dashboard_candidates) &&
      frameAnalysis.dashboard_candidates.length > 0
    ) {
      return false;
    }
    return true;
  });

  return missing.length > 0
    ? missing.map((section) => `Add clear ${displayViewName(section)} photo/video frame.`)
    : ["All required auction photo sections have routed inspection images."];
}

function buildConditionGrade(
  damage: any,
  gemini: any,
  pipelineAudit: PipelineAudit | undefined,
): string {
  const severity = cleanText(damage?.severity).toLowerCase();
  const condition = cleanText(gemini?.overall_condition || gemini?.condition).toLowerCase();
  const damageCount = buildDamageItems(damage, gemini, null).length;
  const hasAuditFailures = Boolean(pipelineAudit && pipelineAudit.status !== "complete");

  if (severity === "high" || condition === "poor") return "D - Significant issues disclosed";
  if (severity === "medium" || condition === "fair" || damageCount >= 3) return "C - Visible issues, review closely";
  if (hasAuditFailures || damageCount > 0 || severity === "low") return "B - Presentable with disclosed findings";
  if (condition === "excellent") return "A - Clean visible condition";
  return "B - Good visible condition";
}

function buildAiListingContent({
  inspection,
  vehicleInfo,
  odometer,
  damage,
  exhaust,
  report,
  gemini,
  inspectionAnalysis,
  frameAnalysis,
  pipelineAudit,
  visualAnalysis,
}: {
  inspection: any;
  vehicleInfo: Record<string, any>;
  odometer: Record<string, any>;
  damage: any;
  exhaust: Record<string, any>;
  report: Record<string, any> | null;
  gemini: any;
  inspectionAnalysis: any;
  frameAnalysis: any;
  pipelineAudit?: PipelineAudit;
  visualAnalysis: any;
}): AiListingBuilderContent {
  const title = uniqueList([
    vehicleInfo.year,
    vehicleInfo.brand,
    vehicleInfo.model,
    vehicleInfo.variant,
  ]).join(" ") || "Vehicle inspection listing";
  const damageItems = buildDamageItems(damage, gemini, inspectionAnalysis);
  const missingPhotoChecklist = buildMissingPhotoChecklist(inspectionAnalysis, frameAnalysis);
  const failedAuditChecks = Array.isArray(pipelineAudit?.checks)
    ? pipelineAudit.checks.filter((check) => !check?.passed)
    : [];
  const confidenceWarnings = uniqueList([
    typeof vehicleInfo.confidence === "number" && vehicleInfo.confidence < 0.7
      ? `Vehicle identity confidence is ${formatPercent(vehicleInfo.confidence)}.`
      : null,
    typeof odometer.confidence === "number" && odometer.confidence < 0.5
      ? `Odometer confidence is ${formatPercent(odometer.confidence)}.`
      : null,
    visualAnalysis && !visualAnalysis.available
      ? `Visual AI analysis unavailable: ${visualAnalysis.reason || "reason not supplied"}.`
      : null,
    inspectionAnalysis?.consistency?.rejected_count
      ? `${inspectionAnalysis.consistency.rejected_count} inspection image(s) were rejected for quality or routing.`
      : null,
    ...failedAuditChecks.map((check) => `Verification issue: ${String(check.id).replaceAll("_", " ")}.`),
  ]);
  const recommendedDisclosures = uniqueList([
    damageItems.length > 0
      ? "Disclose all AI-detected damage and include close-up photos for each affected area."
      : "State that no visible damage was detected by the current AI pass, subject to buyer review.",
    exhaust?.type ? `Exhaust appears ${exhaust.type}; confirm stock/modified status in seller notes.` : null,
    report?.modification_assessment?.summary
      ? `Modification disclosure: ${report.modification_assessment.summary}`
      : null,
    odometer.value ? `Odometer reading captured as ${odometer.value}; confirm against instrument cluster and title paperwork.` : "Odometer reading is not verified; disclose as unknown until confirmed.",
    vehicleInfo.vin || vehicleInfo.registration
      ? "VIN/registration evidence was supplied; keep it available for buyer verification."
      : "VIN/registration evidence is missing; add it before publishing the listing.",
    confidenceWarnings.length > 0
      ? "Mark listing as needing manual review until confidence warnings are resolved."
      : null,
  ]);
  const shortSummary =
    cleanText(report?.summary) ||
    cleanText(gemini?.summary) ||
    `${title} prepared from AI inspection evidence.`;
  const conditionGrade = buildConditionGrade(damage, gemini, pipelineAudit);
  const buyerFacingReport = [
    `${title}`,
    "",
    shortSummary,
    "",
    `Condition grade: ${conditionGrade}`,
    `Odometer: ${displayValue(odometer.value)}${formatPercent(odometer.confidence) ? ` (${formatPercent(odometer.confidence)} confidence)` : ""}`,
    `Body type/category: ${displayValue(vehicleInfo.vehicle_category || vehicleInfo.category || vehicleInfo.type)}`,
    `Color: ${displayValue(vehicleInfo.color)}`,
    `Inspection ID: ${inspection.id}`,
    "",
    damageItems.length > 0 ? "Detected damage:" : "Detected damage: None reported by current AI pass.",
    ...damageItems.map((item) => `- ${item}`),
    "",
    "Recommended disclosures:",
    ...recommendedDisclosures.map((item) => `- ${item}`),
    "",
    "Missing photo checklist:",
    ...missingPhotoChecklist.map((item) => `- ${item}`),
    "",
    confidenceWarnings.length > 0 ? "Confidence warnings:" : "Confidence warnings: none.",
    ...confidenceWarnings.map((item) => `- ${item}`),
  ].join("\n");

  return {
    title,
    shortSummary,
    conditionGrade,
    detectedDamageList: damageItems.length > 0 ? damageItems : ["No visible damage detected by current AI evidence."],
    recommendedDisclosures,
    missingPhotoChecklist,
    confidenceWarnings: confidenceWarnings.length > 0 ? confidenceWarnings : ["No major confidence warnings from current artifacts."],
    buyerFacingReport,
  };
}

function escapePdfText(value: string): string {
  return value
    .replace(/\\/g, "\\\\")
    .replace(/\(/g, "\\(")
    .replace(/\)/g, "\\)");
}

function wrapPdfLine(line: string, maxLength = 92): string[] {
  const words = line.split(/\s+/).filter(Boolean);
  const lines: string[] = [];
  let current = "";
  words.forEach((word) => {
    const next = current ? `${current} ${word}` : word;
    if (next.length > maxLength && current) {
      lines.push(current);
      current = word;
    } else {
      current = next;
    }
  });
  if (current || line.trim() === "") lines.push(current);
  return lines;
}

function buildPdfPages(lines: string[]): string[][] {
  const pages: string[][] = [[]];
  let lineCount = 0;
  lines.forEach((line) => {
    const wrapped = wrapPdfLine(line);
    wrapped.forEach((wrappedLine) => {
      if (lineCount >= 48) {
        pages.push([]);
        lineCount = 0;
      }
      pages[pages.length - 1].push(wrappedLine);
      lineCount += 1;
    });
  });
  return pages;
}

function createTextPdfBlob(title: string, lines: string[]): Blob {
  const pages = buildPdfPages(lines);
  const objects: string[] = [];
  objects.push("<< /Type /Catalog /Pages 2 0 R >>");
  const pageObjectIds = pages.map((_, index) => 4 + index * 2);
  objects.push(`<< /Type /Pages /Kids [${pageObjectIds.map((id) => `${id} 0 R`).join(" ")}] /Count ${pages.length} >>`);
  objects.push("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>");

  pages.forEach((pageLines, index) => {
    const pageObjectId = 4 + index * 2;
    const contentObjectId = pageObjectId + 1;
    const contentLines = [
      "BT",
      "/F1 10 Tf",
      "50 792 Td",
      "14 TL",
      ...pageLines.map((line) => `(${escapePdfText(line)}) Tj T*`),
      "ET",
    ];
    const content = contentLines.join("\n");
    objects.push(`<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R >> >> /Contents ${contentObjectId} 0 R >>`);
    objects.push(`<< /Length ${content.length} >>\nstream\n${content}\nendstream`);
  });

  let pdf = `%PDF-1.4\n% ${escapePdfText(title)}\n`;
  const offsets = [0];
  objects.forEach((object, index) => {
    offsets.push(pdf.length);
    pdf += `${index + 1} 0 obj\n${object}\nendobj\n`;
  });
  const xrefOffset = pdf.length;
  pdf += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  offsets.slice(1).forEach((offset) => {
    pdf += `${String(offset).padStart(10, "0")} 00000 n \n`;
  });
  pdf += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xrefOffset}\n%%EOF`;
  return new Blob([pdf], { type: "application/pdf" });
}

function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function downloadAiListingPdf(listing: AiListingBuilderContent, inspectionId: string): void {
  const lines = [
    "AI AUCTION LISTING REPORT",
    "",
    `Title: ${listing.title}`,
    `Condition grade: ${listing.conditionGrade}`,
    "",
    "Short summary:",
    listing.shortSummary,
    "",
    "Detected damage list:",
    ...listing.detectedDamageList.map((item) => `- ${item}`),
    "",
    "Recommended disclosures:",
    ...listing.recommendedDisclosures.map((item) => `- ${item}`),
    "",
    "Missing-photo checklist:",
    ...listing.missingPhotoChecklist.map((item) => `- ${item}`),
    "",
    "Confidence warnings:",
    ...listing.confidenceWarnings.map((item) => `- ${item}`),
    "",
    "Buyer-facing report:",
    ...listing.buyerFacingReport.split("\n"),
  ];
  downloadBlob(
    createTextPdfBlob(listing.title, lines),
    `ai-listing-${inspectionId}.pdf`,
  );
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

function ListingBuilderList({
  title,
  items,
}: {
  title: string;
  items: string[];
}) {
  return (
    <div className="rounded-lg border border-border bg-background/60 p-3">
      <h4 className="mb-2 text-sm font-semibold">{title}</h4>
      <ul className="list-inside list-disc space-y-1 text-sm text-muted-foreground">
        {items.map((item, index) => (
          <li key={`${title}-${index}`}>{item}</li>
        ))}
      </ul>
    </div>
  );
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
  const inspectionAnalysis = report?.inspection_analysis;
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
  const organizedShots = REVIEW_VIEW_ORDER
    .map((view) => {
      const shot = frameAnalysis?.angle_shots?.[view];
      return shot ? { view, ...shot } : null;
    })
    .filter(Boolean);
  const dashboardCandidates = Array.isArray(frameAnalysis?.dashboard_candidates)
    ? frameAnalysis.dashboard_candidates.slice(0, 6)
    : [];
  const reviewShots = buildReviewShots(frameAnalysis, inspectionAnalysis);
  const damageLocations = normalizeDamageLocations(damage);
  const aiListing = buildAiListingContent({
    inspection,
    vehicleInfo,
    odometer,
    damage,
    exhaust,
    report,
    gemini,
    inspectionAnalysis,
    frameAnalysis,
    pipelineAudit,
    visualAnalysis,
  });

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

      <Card className="overflow-hidden">
        <CardHeader className="border-b border-border bg-secondary/30">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <CardTitle className="flex items-center gap-2">
              <FileText className="h-5 w-5 text-primary" />
              AI Listing Builder
            </CardTitle>
            <Button
              type="button"
              variant="outline"
              className="w-fit gap-2"
              onClick={() => downloadAiListingPdf(aiListing, inspection.id)}
            >
              <Download className="h-4 w-4" />
              Download Listing PDF
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 md:grid-cols-[1.25fr_0.75fr]">
            <div>
              <p className="font-mono text-[11px] uppercase tracking-normal text-muted-foreground">
                Auction title
              </p>
              <h3 className="mt-1 text-lg font-semibold">{aiListing.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                Listing summary: {aiListing.shortSummary}
              </p>
            </div>
            <div className="rounded-lg border border-border bg-background/60 p-3">
              <p className="font-mono text-[11px] uppercase tracking-normal text-muted-foreground">
                Condition grade
              </p>
              <p className="mt-1 text-base font-semibold">{aiListing.conditionGrade}</p>
            </div>
          </div>

          <div className="grid gap-3 lg:grid-cols-2">
            <ListingBuilderList
              title="Detected damage list"
              items={aiListing.detectedDamageList}
            />
            <ListingBuilderList
              title="Recommended disclosures"
              items={aiListing.recommendedDisclosures}
            />
            <ListingBuilderList
              title="Missing-photo checklist"
              items={aiListing.missingPhotoChecklist}
            />
            <ListingBuilderList
              title="Confidence warnings"
              items={aiListing.confidenceWarnings}
            />
          </div>

          <div className="rounded-lg border border-border bg-background/60 p-3">
            <h4 className="mb-2 text-sm font-semibold">Buyer-facing report</h4>
            <p className="whitespace-pre-line text-sm leading-relaxed text-muted-foreground">
              {aiListing.buyerFacingReport}
            </p>
          </div>
        </CardContent>
      </Card>

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

      {reviewShots.length > 0 && (
        <InspectionImageReview
          shots={reviewShots}
          damageLocations={damageLocations}
          coverage={frameAnalysis?.coverage}
          framesAnalyzed={frameAnalysis?.frames_analyzed}
          angleCount={organizedShots.length}
          dashboardCount={dashboardCandidates.length}
        />
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

function InspectionImageReview({
  shots,
  damageLocations,
  coverage,
  framesAnalyzed,
  angleCount,
  dashboardCount,
}: {
  shots: ReviewShot[];
  damageLocations: DamageLocation[];
  coverage?: any;
  framesAnalyzed?: number;
  angleCount: number;
  dashboardCount: number;
}) {
  const exteriorShots = useMemo(() => orderedShots(shots, EXTERIOR_360_ORDER), [shots]);
  const interiorShots = useMemo(() => orderedShots(shots, DETAIL_360_ORDER), [shots]);
  const [mode, setMode] = useState<"exterior" | "interior">(
    exteriorShots.length > 0 ? "exterior" : "interior",
  );
  const [activeIndex, setActiveIndex] = useState(0);
  const [zoom, setZoom] = useState(1);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [naturalSize, setNaturalSize] = useState({ width: 0, height: 0 });
  const stageRef = useRef<HTMLDivElement | null>(null);
  const dragRef = useRef<{ pointerId: number; startX: number; startIndex: number } | null>(null);
  const mouseDragRef = useRef<{ startX: number; startIndex: number } | null>(null);
  const activeShots =
    mode === "exterior"
      ? exteriorShots.length > 0 ? exteriorShots : shots
      : interiorShots.length > 0 ? interiorShots : shots;
  const activeShot = activeShots[Math.min(activeIndex, activeShots.length - 1)] || activeShots[0] || shots[0];
  const activePath = uploadPath(activeShot?.imagePath);
  const activeSrc = activePath ? `${BACKEND_BASE_URL}/${activePath}` : "";
  const activeDamageLocations = damageLocations.filter((location) => damageMatchesShot(location, activeShot));

  useEffect(() => {
    setActiveIndex(0);
    setZoom(1);
  }, [mode]);

  useEffect(() => {
    setNaturalSize({ width: 0, height: 0 });
  }, [activeSrc]);

  const selectIndex = (index: number) => {
    const nextIndex = Math.max(0, Math.min(index, activeShots.length - 1));
    setActiveIndex(nextIndex);
    setZoom(1);
  };

  const step = (direction: -1 | 1) => {
    selectIndex((activeIndex + direction + activeShots.length) % activeShots.length);
  };

  const rotateFromDrag = (startX: number, currentX: number, startIndex: number) => {
    const frameStep = Math.round((startX - currentX) / 42);
    const nextIndex = (startIndex + frameStep + activeShots.length * 8) % activeShots.length;
    if (nextIndex !== activeIndex) setActiveIndex(nextIndex);
  };

  const selectDamageLocation = (location: DamageLocation) => {
    const targetMode =
      interiorShots.some((shot) => damageMatchesShot(location, shot)) &&
      !exteriorShots.some((shot) => damageMatchesShot(location, shot))
        ? "interior"
        : "exterior";
    const targetShots = targetMode === "interior" ? interiorShots : exteriorShots;
    const targetIndex = targetShots.findIndex((shot) => damageMatchesShot(location, shot));
    if (targetMode !== mode) setMode(targetMode);
    setActiveIndex(targetIndex >= 0 ? targetIndex : 0);
    setZoom(1.25);
  };

  const onPointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    if (activeShots.length <= 1) return;
    dragRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startIndex: activeIndex,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const onPointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId || activeShots.length <= 1) return;
    rotateFromDrag(drag.startX, event.clientX, drag.startIndex);
  };

  const clearDrag = () => {
    dragRef.current = null;
    mouseDragRef.current = null;
  };

  const onMouseDown = (event: React.MouseEvent<HTMLDivElement>) => {
    if (activeShots.length <= 1) return;
    mouseDragRef.current = {
      startX: event.clientX,
      startIndex: activeIndex,
    };
  };

  const onMouseMove = (event: React.MouseEvent<HTMLDivElement>) => {
    const drag = mouseDragRef.current;
    if (!drag || activeShots.length <= 1) return;
    rotateFromDrag(drag.startX, event.clientX, drag.startIndex);
  };

  const onWheel = (event: React.WheelEvent<HTMLDivElement>) => {
    if (!event.ctrlKey && Math.abs(event.deltaY) < Math.abs(event.deltaX)) return;
    event.preventDefault();
    setZoom((value) => Math.min(3, Math.max(1, value + (event.deltaY < 0 ? 0.15 : -0.15))));
  };

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (activeShots.length === 0) return;
      if (event.key === "ArrowRight") {
        setActiveIndex((current) => (current + 1 + activeShots.length) % activeShots.length);
        setZoom(1);
      }
      if (event.key === "ArrowLeft") {
        setActiveIndex((current) => (current - 1 + activeShots.length) % activeShots.length);
        setZoom(1);
      }
      if (event.key === "Escape") setIsFullscreen(false);
      if (event.key === "+" || event.key === "=") setZoom((value) => Math.min(3, value + 0.25));
      if (event.key === "-") setZoom((value) => Math.max(1, value - 0.25));
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [activeShots.length]);

  const viewer = (
    <div
      data-testid="inspection-360-viewer"
      className={
        isFullscreen
          ? "fixed inset-0 z-50 flex flex-col bg-background"
          : "grid gap-4 lg:grid-cols-[minmax(0,1fr)_260px]"
      }
    >
      <div className="min-w-0">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div>
            <h4 className="text-sm font-semibold capitalize">{displayViewName(activeShot.view)}</h4>
            <p className="text-xs text-muted-foreground">
              {mode === "exterior" ? "Exterior 360" : "Inspection detail"}
              {typeof activeShot.qualityScore === "number"
                ? ` · quality ${Math.round(activeShot.qualityScore * 100)}%`
                : ""}
              {typeof activeShot.timestampSeconds === "number"
                ? ` · ${activeShot.timestampSeconds.toFixed(1)}s`
                : ""}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-1">
            {interiorShots.length > 0 && exteriorShots.length > 0 && (
              <div className="mr-1 grid grid-cols-2 rounded-md border border-border bg-background p-0.5">
                <Button
                  type="button"
                  variant={mode === "exterior" ? "secondary" : "ghost"}
                  size="sm"
                  className="h-8 rounded"
                  onClick={() => setMode("exterior")}
                >
                  Exterior
                </Button>
                <Button
                  type="button"
                  variant={mode === "interior" ? "secondary" : "ghost"}
                  size="sm"
                  className="h-8 rounded"
                  onClick={() => setMode("interior")}
                >
                  Details
                </Button>
              </div>
            )}
            <Button type="button" variant="outline" size="icon" onClick={() => step(-1)} aria-label="Previous image">
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <Button type="button" variant="outline" size="icon" onClick={() => step(1)} aria-label="Next image">
              <ChevronRight className="h-4 w-4" />
            </Button>
            <Button
              type="button"
              variant="outline"
              size="icon"
              onClick={() => setZoom((value) => Math.max(1, value - 0.25))}
              aria-label="Zoom out"
            >
              <ZoomOut className="h-4 w-4" />
            </Button>
            <Button
              type="button"
              variant="outline"
              size="icon"
              onClick={() => setZoom((value) => Math.min(3, value + 0.25))}
              aria-label="Zoom in"
            >
              <ZoomIn className="h-4 w-4" />
            </Button>
            <Button type="button" variant="outline" size="icon" onClick={() => setZoom(1)} aria-label="Reset zoom">
              <RotateCcw className="h-4 w-4" />
            </Button>
            <Button
              type="button"
              variant="outline"
              size="icon"
              onClick={() => setIsFullscreen((value) => !value)}
              aria-label={isFullscreen ? "Exit fullscreen" : "Open fullscreen"}
            >
              {isFullscreen ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
            </Button>
          </div>
        </div>
        <div
          ref={stageRef}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={clearDrag}
          onPointerCancel={clearDrag}
          onMouseDown={onMouseDown}
          onMouseMove={onMouseMove}
          onMouseUp={clearDrag}
          onMouseLeave={clearDrag}
          onWheel={onWheel}
          className={
            isFullscreen
              ? "min-h-0 flex-1 touch-pan-y overflow-auto bg-black"
              : "h-[54vh] min-h-[360px] touch-pan-y overflow-auto rounded-lg border border-border bg-black"
          }
        >
          {activeSrc && (
            <div
              className="relative mx-auto"
              style={{
                width: `${zoom * 100}%`,
                minWidth: "100%",
              }}
            >
              <img
                data-testid="active-360-image"
                src={activeSrc}
                alt={`${displayViewName(activeShot.view)} inspection image`}
                draggable={false}
                onLoad={(event) => {
                  setNaturalSize({
                    width: event.currentTarget.naturalWidth,
                    height: event.currentTarget.naturalHeight,
                  });
                }}
                className="block h-auto w-full select-none transition-opacity duration-150"
              />
              {naturalSize.width > 0 &&
                naturalSize.height > 0 &&
                activeDamageLocations.map((location) => {
                  if (!location.bbox) return null;
                  const [x1, y1, x2, y2] = location.bbox;
                  const width = Math.max(1, x2 - x1);
                  const height = Math.max(1, y2 - y1);
                  return (
                    <button
                      type="button"
                      data-testid="damage-overlay"
                      key={location.id}
                      onClick={() => selectDamageLocation(location)}
                      className="absolute rounded border-2 border-destructive bg-destructive/15 shadow-[0_0_0_9999px_rgba(0,0,0,0.02)] transition hover:bg-destructive/25"
                      style={{
                        left: `${(x1 / naturalSize.width) * 100}%`,
                        top: `${(y1 / naturalSize.height) * 100}%`,
                        width: `${(width / naturalSize.width) * 100}%`,
                        height: `${(height / naturalSize.height) * 100}%`,
                      }}
                      aria-label={`${displayViewName(location.type)} damage overlay`}
                    />
                  );
                })}
            </div>
          )}
        </div>
      </div>

      <div className={isFullscreen ? "border-t border-border bg-background p-3" : "min-w-0"}>
        {damageLocations.length > 0 && (
          <div className="mb-4 rounded-lg border border-border bg-background">
            <div className="flex items-center justify-between gap-2 border-b border-border px-3 py-2">
              <h4 className="text-sm font-semibold">AI Damage Report</h4>
              <Badge variant="outline" className="rounded-md font-mono text-[11px] tracking-normal">
                {damageLocations.length}
              </Badge>
            </div>
            <div className="max-h-52 overflow-y-auto p-2">
              {damageLocations.map((location) => (
                <button
                  type="button"
                  data-testid="damage-report-row"
                  key={location.id}
                  onClick={() => selectDamageLocation(location)}
                  className="mb-1 grid w-full grid-cols-[1fr_auto] gap-2 rounded-md px-2 py-2 text-left text-xs transition hover:bg-secondary"
                >
                  <span className="min-w-0">
                    <span className="block truncate font-medium capitalize text-foreground">
                      {displayViewName(location.type)}
                      {location.angle || location.linkedView ? ` · ${displayViewName(location.angle || location.linkedView || "")}` : ""}
                    </span>
                    <span className="text-muted-foreground">
                      {location.severity || "severity unknown"}
                    </span>
                  </span>
                  {typeof location.confidence === "number" && (
                    <span className="font-mono text-muted-foreground">
                      {Math.round(location.confidence * 100)}%
                    </span>
                  )}
                </button>
              ))}
            </div>
          </div>
        )}
        <div className="mb-3 flex items-center justify-between gap-2">
          <h4 className="text-sm font-semibold">360 Frames</h4>
          {typeof framesAnalyzed === "number" && (
            <span className="text-xs text-muted-foreground">{framesAnalyzed} frames analyzed</span>
          )}
        </div>
        <div
          className={
            isFullscreen
              ? "flex gap-2 overflow-x-auto pb-1"
              : "grid max-h-[54vh] grid-cols-2 gap-2 overflow-y-auto pr-1"
          }
        >
          {activeShots.map((shot, index) => {
            const previewPath = uploadPath(shot.previewPath || shot.imagePath);
            if (!previewPath) return null;
            const isActive = index === activeIndex;
            const shotDamageCount = damageLocations.filter((location) => damageMatchesShot(location, shot)).length;
            return (
              <button
                type="button"
                key={shot.id}
                onClick={() => selectIndex(index)}
                className={`min-w-0 overflow-hidden rounded-lg border bg-background text-left transition ${
                  isActive ? "border-primary ring-2 ring-primary/25" : "border-border hover:border-primary/60"
                } ${isFullscreen ? "w-36 shrink-0" : ""}`}
              >
                <div className="relative aspect-video bg-black">
                  <img
                    src={`${BACKEND_BASE_URL}/${previewPath}`}
                    alt={`${displayViewName(shot.view)} preview`}
                    className="h-full w-full object-cover"
                  />
                  {shotDamageCount > 0 && (
                    <span className="absolute right-1 top-1 rounded bg-destructive px-1.5 py-0.5 font-mono text-[10px] text-destructive-foreground">
                      {shotDamageCount}
                    </span>
                  )}
                </div>
                <div className="flex items-center justify-between gap-2 px-2 py-1.5 text-xs">
                  <span className="truncate font-medium capitalize">{displayViewName(shot.view)}</span>
                  {typeof shot.score === "number" && (
                    <span className="font-mono text-muted-foreground">{Math.round(shot.score * 100)}%</span>
                  )}
                </div>
              </button>
            );
          })}
        </div>
        {dashboardCount > 0 && (
          <div className="mt-3 flex items-center justify-between gap-2 text-xs text-muted-foreground">
            <span className="flex items-center gap-2">
              <Gauge className="h-4 w-4" />
              Dashboard candidates
            </span>
            <span className="font-mono">{dashboardCount}</span>
          </div>
        )}
      </div>
    </div>
  );

  if (isFullscreen) return viewer;

  return (
    <Card className="overflow-hidden">
      <CardHeader className="border-b border-border bg-secondary/30">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <CardTitle className="flex items-center gap-2">
            <Camera className="h-5 w-5 text-primary" />
            Interactive 360 Inspection Viewer
          </CardTitle>
          {coverage && (
            <div className="flex flex-wrap gap-2">
              <Badge variant="outline" className="w-fit rounded-md bg-background font-mono text-[11px] uppercase tracking-normal">
                {Math.round((coverage.ratio || 0) * 100)}% selected
              </Badge>
              {typeof coverage.high_confidence_ratio === "number" && (
                <Badge variant="outline" className="w-fit rounded-md bg-background font-mono text-[11px] uppercase tracking-normal">
                  {Math.round((coverage.high_confidence_ratio || 0) * 100)}% high confidence
                </Badge>
              )}
              <Badge variant="outline" className="w-fit rounded-md bg-background font-mono text-[11px] uppercase tracking-normal">
                {angleCount} angle shots
              </Badge>
            </div>
          )}
        </div>
      </CardHeader>
      <CardContent>{viewer}</CardContent>
    </Card>
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
