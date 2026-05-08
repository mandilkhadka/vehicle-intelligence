"use client";

import Image from "next/image";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { BACKEND_BASE_URL } from "@/lib/api";
import { cn } from "@/lib/utils";

interface DamageLocation {
  type?: string;
  frame?: string;
  snapshot?: string;
  confidence?: number;
  bbox?: [number, number, number, number];
}

interface DamageInfoProps {
  damage?: {
    scratches?: { count?: number; detected?: boolean };
    dents?: { count?: number; detected?: boolean };
    rust?: { count?: number; detected?: boolean };
    severity?: string;
    locations?: DamageLocation[];
  };
}

const SEVERITY_STYLES: Record<string, string> = {
  high: "border-destructive/40 bg-destructive/10 text-destructive",
  medium: "border-amber-500/40 bg-amber-500/10 text-amber-600 dark:text-amber-400",
  low: "border-emerald-500/40 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
};

export default function DamageInfo({ damage }: DamageInfoProps) {
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
  const total = scratches + dents + rust;
  const severity = (damage.severity || "low").toLowerCase();
  const visibleSnapshots =
    damage.locations?.filter((l) => l.snapshot && (l.confidence || 0) >= 0.3).slice(0, 9) || [];

  return (
    <Card className="md:col-span-2">
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle>Damage</CardTitle>
        <Badge variant="outline" className={cn(SEVERITY_STYLES[severity] || SEVERITY_STYLES.low)}>
          {severity.toUpperCase()}
        </Badge>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-3 gap-3">
          <Stat label="Scratches" value={scratches} />
          <Stat label="Dents" value={dents} />
          <Stat label="Rust" value={rust} />
        </div>

        <p className="text-sm text-muted-foreground">
          {total === 0
            ? "No significant damage detected."
            : `${total} damage area${total > 1 ? "s" : ""} detected.`}
        </p>

        {visibleSnapshots.length > 0 && (
          <div>
            <h4 className="mb-3 text-sm font-medium">Snapshots</h4>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              {visibleSnapshots.map((loc, i) => {
                const path = loc.snapshot!.startsWith("uploads/")
                  ? loc.snapshot!
                  : `uploads/${loc.snapshot}`;
                const pct = Math.round((loc.confidence || 0) * 100);
                return (
                  <div
                    key={i}
                    className="relative aspect-square overflow-hidden rounded-lg border border-border"
                  >
                    <Image
                      src={`${BACKEND_BASE_URL}/${path}`}
                      alt={`${loc.type || "Damage"} ${i + 1}`}
                      fill
                      className="object-cover"
                      sizes="(max-width: 768px) 50vw, 33vw"
                    />
                    <div className="absolute right-1.5 top-1.5 rounded-md bg-background/80 px-1.5 py-0.5 text-xs font-semibold backdrop-blur-sm">
                      {pct}%
                    </div>
                    <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/70 to-transparent px-2 py-1.5 text-xs font-medium capitalize text-white">
                      {loc.type || "damage"}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
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
