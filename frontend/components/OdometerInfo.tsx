"use client";

import Image from "next/image";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { uploadSrc } from "@/lib/format";

interface OdometerInfoProps {
  odometer?: {
    value?: number | null;
    confidence?: number;
    speedometer_image_path?: string | null;
    source_frame_index?: number | null;
    timestamp_seconds?: number | null;
    source_frame_path?: string | null;
    organized_frame_path?: string | null;
    crop_path?: string | null;
    readout_crop_path?: string | null;
    notes?: string | null;
    reason?: string | null;
    reasoning?: string | null;
    alternatives?: Array<{
      value?: number | null;
      confidence?: number;
      occurrences?: number;
      digit_count?: number;
      preprocessing?: string[];
    }>;
  };
}

export default function OdometerInfo({ odometer }: OdometerInfoProps) {
  if (!odometer) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Odometer</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">No odometer data available</p>
        </CardContent>
      </Card>
    );
  }

  const pct = Math.round((odometer.confidence || 0) * 100);
  const status = odometer.value == null ? "Unverified" : pct >= 70 ? "Verified" : "Candidate";
  const value =
    odometer.value !== null && odometer.value !== undefined
      ? `${odometer.value.toLocaleString()} km`
      : "Not detected";
  const note = odometer.notes || odometer.reason || odometer.reasoning;

  const imgSrc = uploadSrc(
    odometer.readout_crop_path || odometer.crop_path || odometer.speedometer_image_path,
  );

  const statusBadgeClass =
    status === "Verified"
      ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
      : status === "Candidate"
        ? "border-amber-500/40 bg-amber-500/10 text-amber-600 dark:text-amber-400"
        : "border-border bg-secondary/40 text-muted-foreground";

  return (
    <Card>
      <CardHeader>
        <CardTitle>Odometer</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-2xl font-bold tracking-tight">{value}</p>
            <Badge variant="outline" className={statusBadgeClass}>
              {status}
            </Badge>
          </div>
          {note && (
            <p className="mt-2 text-sm text-muted-foreground">{note}</p>
          )}
        </div>
        {(odometer.source_frame_index != null || odometer.timestamp_seconds != null) && (
          <div className="grid grid-cols-2 gap-3 text-sm">
            {odometer.source_frame_index != null && (
              <div>
                <p className="text-muted-foreground">Source frame</p>
                <p className="font-medium">{odometer.source_frame_index}</p>
              </div>
            )}
            {odometer.timestamp_seconds != null && (
              <div>
                <p className="text-muted-foreground">Timestamp</p>
                <p className="font-medium">{Number(odometer.timestamp_seconds).toFixed(2)}s</p>
              </div>
            )}
          </div>
        )}
        <div>
          <div className="mb-1 flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Confidence</span>
            <span className="font-medium">{pct}%</span>
          </div>
          <Progress value={pct} className="h-1.5" />
        </div>
        {Array.isArray(odometer.alternatives) && odometer.alternatives.length > 0 && (
          <div className="space-y-2 text-sm">
            <p className="font-medium">Alternative OCR candidates</p>
            <div className="grid gap-2">
              {odometer.alternatives.slice(0, 4).map((item, index) => (
                <div
                  key={`${item.value ?? "unknown"}-${index}`}
                  className="flex items-center justify-between rounded border border-border px-3 py-2"
                >
                  <span>{item.value != null ? `${item.value.toLocaleString()} km` : "Unknown"}</span>
                  <span className="text-muted-foreground">
                    {Math.round((item.confidence || 0) * 100)}%
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
        {imgSrc && (
          <div className="relative aspect-video overflow-hidden rounded-lg border border-border bg-secondary/40">
            <Image
              src={imgSrc}
              alt="Odometer readout"
              fill
              className="object-contain"
              unoptimized
            />
          </div>
        )}
      </CardContent>
    </Card>
  );
}
