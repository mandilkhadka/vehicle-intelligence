"use client";

import Image from "next/image";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { BACKEND_BASE_URL } from "@/lib/api";

interface OdometerInfoProps {
  odometer?: {
    value?: number | null;
    confidence?: number;
    speedometer_image_path?: string | null;
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
  const value =
    odometer.value !== null && odometer.value !== undefined
      ? `${odometer.value.toLocaleString()} km`
      : "Not detected";

  const imgPath = odometer.speedometer_image_path
    ? `uploads/${odometer.speedometer_image_path.replace(/^.*uploads\//, "")}`
    : null;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Odometer</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div>
          <p className="text-2xl font-bold tracking-tight">{value}</p>
        </div>
        <div>
          <div className="mb-1 flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Confidence</span>
            <span className="font-medium">{pct}%</span>
          </div>
          <Progress value={pct} className="h-1.5" />
        </div>
        {imgPath && (
          <div className="relative aspect-video overflow-hidden rounded-lg border border-border bg-secondary/40">
            <Image
              src={`${BACKEND_BASE_URL}/${imgPath}`}
              alt="Speedometer"
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
