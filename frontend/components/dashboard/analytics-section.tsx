"use client";

import { TrendChart } from "./trend-chart";
import { DamageChart } from "./damage-chart";
import { VehicleChart } from "./vehicle-chart";
import { MetricsResponse } from "@/lib/api";

interface AnalyticsSectionProps {
  metrics: MetricsResponse | null;
  isLoading: boolean;
}

export function AnalyticsSection({ metrics, isLoading }: AnalyticsSectionProps) {
  const emptyDamage = { scratches: 0, dents: 0, rust: 0 };
  const emptyTrend: Array<{ date: string; issues: number }> = [];
  const emptyVehicles: Array<{ brand: string; count: number }> = [];

  return (
    <div className="flex flex-col gap-4">
      <TrendChart
        data={metrics?.dailyTrend ?? emptyTrend}
        isLoading={isLoading}
      />
      <DamageChart
        data={metrics?.damageBreakdown ?? emptyDamage}
        isLoading={isLoading}
      />
      <VehicleChart
        data={metrics?.vehicleBreakdown ?? emptyVehicles}
        isLoading={isLoading}
      />
    </div>
  );
}
