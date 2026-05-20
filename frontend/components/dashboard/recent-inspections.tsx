"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { AlertTriangle, ArrowRight, ChevronRight, Loader2, ShieldCheck } from "lucide-react";
import { getInspections, BACKEND_BASE_URL } from "@/lib/api";
import { showError } from "@/lib/toast";
import { safeParseJsonOrValue } from "@/lib/utils/safe-json";
import {
  getAuditBadgeState,
  getInspectionPipelineAudit,
} from "@/lib/inspection-audit";

function formatTimeAgo(date: Date): string {
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 60) {
    return `${diffMins} minute${diffMins !== 1 ? "s" : ""} ago`;
  } else if (diffHours < 24) {
    return `${diffHours} hour${diffHours !== 1 ? "s" : ""} ago`;
  } else if (diffDays < 7) {
    return `${diffDays} day${diffDays !== 1 ? "s" : ""} ago`;
  } else {
    return date.toLocaleDateString();
  }
}

function getStatusBadge(status: string) {
  switch (status) {
    case "completed":
      return (
        <Badge className="bg-emerald-500/10 text-emerald-500 hover:bg-emerald-500/20">
          Completed
        </Badge>
      );
    case "processing":
      return (
        <Badge className="bg-primary/10 text-primary hover:bg-primary/20">
          Processing
        </Badge>
      );
    case "failed":
      return (
        <Badge className="bg-destructive/10 text-destructive hover:bg-destructive/20">
          Failed
        </Badge>
      );
    default:
      return <Badge variant="secondary">{status}</Badge>;
  }
}

function getVerificationBadge(state: ReturnType<typeof getAuditBadgeState>) {
  if (state.status === "verified") {
    return (
      <Badge className="gap-1 bg-emerald-500/10 text-emerald-500 hover:bg-emerald-500/20">
        <ShieldCheck className="h-3 w-3" />
        Verified
      </Badge>
    );
  }

  if (state.status === "review") {
    return (
      <Badge variant="outline" className="gap-1 border-accent/40 text-accent">
        <AlertTriangle className="h-3 w-3" />
        Needs review
      </Badge>
    );
  }

  return null;
}

export function RecentInspections() {
  const [inspections, setInspections] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchInspections = async () => {
      try {
        const data = await getInspections();
        // Transform and sort by date, get most recent 5
        const transformed = data
          .map((insp: any) => {
            const vehicleInfo = safeParseJsonOrValue<Record<string, any>>(
              insp.vehicle_info as any,
              {},
            );

            const damage = safeParseJsonOrValue<Record<string, any>>(
              insp.damage_summary as any,
              {},
            );

            const issues =
              (damage.scratches?.count || 0) +
              (damage.dents?.count || 0) +
              (damage.rust?.count || 0) +
              (damage.cracks?.count || 0) +
              (damage.paint_damage?.count || 0);

            const frames = safeParseJsonOrValue<string[]>(
              insp.extracted_frames as any,
              [],
            );

            const isReal = (v: unknown): v is string =>
              typeof v === "string" && v.trim() !== "" && v !== "Unknown";
            const brand = (isReal(vehicleInfo.brand) && vehicleInfo.brand) || (isReal(insp.vehicle_brand) && insp.vehicle_brand) || "";
            const model = (isReal(vehicleInfo.model) && vehicleInfo.model) || (isReal(insp.vehicle_model) && insp.vehicle_model) || "";
            const year =
              vehicleInfo.year ? String(vehicleInfo.year) :
              (isReal(insp.vehicle_year) && insp.vehicle_year) || "";
            const variant =
              vehicleInfo.variant ? String(vehicleInfo.variant) :
              (isReal(insp.vehicle_variant) && insp.vehicle_variant) || "";
            const vehicle = [year, brand, model, variant].filter(Boolean).join(" ").trim() || "Unidentified vehicle";
            const audit = getInspectionPipelineAudit(insp);

            return {
              id: insp.id,
              vehicle,
              brand: brand || "—",
              status: insp.job_status || "completed",
              auditState: getAuditBadgeState(audit),
              issues,
              date: insp.created_at ? new Date(insp.created_at) : new Date(),
              dateString: insp.created_at
                ? formatTimeAgo(new Date(insp.created_at))
                : "—",
              odometer: insp.odometer_value || "N/A",
              image: (() => {
                // Skip known-dead paths from old MOCK_MODE rows.
                const f = frames[0];
                if (!f || typeof f !== "string" || f.startsWith("frames/sample/")) return null;
                return `${BACKEND_BASE_URL}/${f.startsWith("uploads/") ? f : `uploads/${f}`}`;
              })(),
            };
          })
          .sort((a, b) => b.date.getTime() - a.date.getTime())
          .slice(0, 5);

        setInspections(transformed);
      } catch (err) {
        showError("Failed to fetch inspections", err);
        setInspections([]);
      } finally {
        setLoading(false);
      }
    };

    fetchInspections();
  }, []);

  return (
    <Card className="col-span-2 overflow-hidden">
      <CardHeader className="flex flex-row items-center justify-between">
        <div>
          <CardTitle>Recent Inspections</CardTitle>
          <CardDescription>Latest vehicle analysis results</CardDescription>
        </div>
        <Button variant="ghost" size="sm" className="gap-1" asChild>
          <Link href="/history">
            View all
            <ArrowRight className="h-4 w-4" />
          </Link>
        </Button>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-6 w-6 animate-spin text-primary" />
          </div>
        ) : inspections.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            No inspections yet
          </div>
        ) : (
          <div className="space-y-1">
            {inspections.map((inspection) => (
              <Link
                key={inspection.id}
                href={`/inspection/${inspection.id}`}
              className="group flex items-center justify-between rounded-lg p-3 transition-colors hover:bg-secondary/50 cursor-pointer"
              >
                <div className="flex items-center gap-4">
                  {inspection.image ? (
                    <div className="relative h-12 w-16 overflow-hidden rounded-lg">
                      <Image
                        src={inspection.image || "/placeholder.svg"}
                        alt={inspection.vehicle}
                        fill
                        className="object-cover"
                        unoptimized
                      />
                    </div>
                  ) : (
                    <div className="flex h-12 w-16 items-center justify-center rounded-lg bg-secondary text-xs font-medium text-muted-foreground">
                      {inspection.brand.slice(0, 2).toUpperCase()}
                    </div>
                  )}
                  <div>
                    <p className="font-medium">{inspection.vehicle}</p>
                    <p className="text-sm text-muted-foreground">
                      {inspection.id} · {inspection.odometer}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-4">
                  <div className="text-right">
                    <div className="flex flex-col items-end gap-1">
                      {getStatusBadge(inspection.status)}
                      {getVerificationBadge(inspection.auditState)}
                    </div>
                    {inspection.status === "completed" &&
                      inspection.issues > 0 && (
                        <p className="mt-1 text-xs text-muted-foreground">
                          {inspection.issues} issue
                          {inspection.issues > 1 ? "s" : ""} found
                        </p>
                      )}
                  </div>
                  <div className="text-right text-sm text-muted-foreground">
                    {inspection.dateString}
                  </div>
                  <ChevronRight className="h-4 w-4 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
                </div>
              </Link>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
