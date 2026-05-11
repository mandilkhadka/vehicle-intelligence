"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import Image from "next/image";
import { BrainCircuit, Download, Loader2 } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import VehicleInfo from "@/components/VehicleInfo";
import OdometerInfo from "@/components/OdometerInfo";
import DamageInfo from "@/components/DamageInfo";
import ExhaustInfo from "@/components/ExhaustInfo";
import { getInspection, BACKEND_BASE_URL } from "@/lib/api";
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
              <InspectionContent inspection={inspection} />
            )}
      </div>
    </AppShell>
  );
}

function InspectionContent({ inspection }: { inspection: any }) {
  const parseMaybe = <T,>(v: string | T | null | undefined, fallback: T) =>
    safeParseJsonOrValue<T>(v, fallback);

  const vehicleInfo =
    parseMaybe(inspection.vehicle_info, null) || {
      type: inspection.vehicle_type,
      brand: inspection.vehicle_brand,
      model: inspection.vehicle_model,
      confidence: inspection.vehicle_confidence,
    };

  const odometer = {
    value: inspection.odometer_value,
    confidence: inspection.odometer_confidence,
    speedometer_image_path: inspection.speedometer_image_path,
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
  const frames = parseMaybe<string[]>(inspection.extracted_frames, []);
  const gemini = report?.gemini_analysis;
  const referenceImage = report?.reference_image || gemini?.reference_image;

  return (
    <div className="space-y-6">
      {report && (report.summary || report.recommendations?.length) && (
        <Card>
          <CardHeader>
            <CardTitle>Summary</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {report.summary && (
              <p className="text-sm leading-relaxed text-foreground">{report.summary}</p>
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

      {gemini?.available && (
        <Card className="overflow-hidden">
          <CardHeader className="border-b border-border bg-secondary/30">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <CardTitle className="flex items-center gap-2">
                <BrainCircuit className="h-5 w-5 text-primary" />
                AI Visual Analysis
              </CardTitle>
              <Badge variant="outline" className="w-fit rounded-md bg-background font-mono text-[11px] uppercase tracking-normal">
                Gemini Vision
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
            {Array.isArray(gemini.per_frame) && gemini.per_frame.length > 0 && (
              <div>
                <h4 className="mb-2 text-sm font-semibold">Per-frame observations</h4>
                <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                  {gemini.per_frame.map((f: any, i: number) => {
                    const path = typeof f.frame === "string"
                      ? (f.frame.startsWith("uploads/") ? f.frame : `uploads/${f.frame.replace(/^.*uploads\//, "")}`)
                      : null;
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
                  const path = frame.startsWith("uploads/")
                    ? frame
                    : `uploads/${frame.replace(/^.*uploads\//, "")}`;
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
