"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";

interface VehicleInfoProps {
  vehicleInfo?: {
    type?: string;
    brand?: string;
    model?: string;
    color?: string;
    confidence?: number;
  };
}

export default function VehicleInfo({ vehicleInfo }: VehicleInfoProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Vehicle</CardTitle>
      </CardHeader>
      <CardContent>
        {!vehicleInfo ? (
          <p className="text-sm text-muted-foreground">No vehicle data available</p>
        ) : (
          <dl className="space-y-3 text-sm">
            <Row label="Type" value={vehicleInfo.type} capitalize />
            <Row label="Brand" value={vehicleInfo.brand} />
            <Row label="Model" value={vehicleInfo.model} />
            {vehicleInfo.color && <Row label="Color" value={vehicleInfo.color} capitalize />}
            <ConfidenceRow value={vehicleInfo.confidence} />
          </dl>
        )}
      </CardContent>
    </Card>
  );
}

function Row({ label, value, capitalize }: { label: string; value?: string; capitalize?: boolean }) {
  return (
    <div className="flex items-center justify-between">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className={capitalize ? "font-medium capitalize" : "font-medium"}>
        {value || "Unknown"}
      </dd>
    </div>
  );
}

function ConfidenceRow({ value }: { value?: number }) {
  const pct = Math.round((value || 0) * 100);
  return (
    <div>
      <div className="mb-1 flex items-center justify-between">
        <dt className="text-muted-foreground">Confidence</dt>
        <dd className="font-medium">{pct}%</dd>
      </div>
      <Progress value={pct} className="h-1.5" />
    </div>
  );
}
