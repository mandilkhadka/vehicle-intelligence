"use client";

import { useCallback, useEffect, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { ArrowRight, ChevronRight, Loader2, RefreshCcw } from "lucide-react";
import { getInspections } from "@/lib/api";
import { showError } from "@/lib/toast";
import {
  toInspectionListItem,
  type InspectionListItem,
} from "@/lib/inspection-summary";
import { StatusBadge, VerificationBadge } from "@/components/status-badge";

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

type RecentRow = InspectionListItem & { dateString: string };

export function RecentInspections() {
  const [inspections, setInspections] = useState<RecentRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);

  const fetchInspections = useCallback(async () => {
    setLoading(true);
    setFailed(false);
    try {
      const data = await getInspections();
      // Transform and sort by date, get most recent 5
      const transformed = data
        .map((insp: any): RecentRow => {
          const item = toInspectionListItem(insp, {
            fallbackVehicleLabel: "Unidentified vehicle",
          });
          return {
            ...item,
            dateString: item.date ? formatTimeAgo(item.date) : "—",
          };
        })
        .sort(
          (a, b) => (b.date?.getTime() ?? 0) - (a.date?.getTime() ?? 0),
        )
        .slice(0, 5);

      setInspections(transformed);
    } catch (err) {
      showError("Failed to fetch inspections", err);
      setInspections([]);
      setFailed(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchInspections();
  }, [fetchInspections]);

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
        ) : failed ? (
          <div className="py-8 text-center">
            <p className="mb-3 text-sm text-destructive">
              Could not load recent inspections.
            </p>
            <Button variant="outline" size="sm" onClick={fetchInspections} className="gap-2">
              <RefreshCcw className="h-4 w-4" /> Retry
            </Button>
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
                      <StatusBadge status={inspection.status} />
                      <VerificationBadge state={inspection.auditState} />
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
