"use client";

/**
 * Damage information display component
 * Shows detected damage (scratches, dents, rust) and severity
 */

import { BACKEND_BASE_URL } from "@/lib/api";
import Image from "next/image";

interface DamageInfoProps {
  damage?: {
    scratches?: {
      count?: number;
      detected?: boolean;
    };
    dents?: {
      count?: number;
      detected?: boolean;
    };
    rust?: {
      count?: number;
      detected?: boolean;
    };
    severity?: string;
    locations?: Array<{
      type?: string;
      frame?: string;
      snapshot?: string;
      confidence?: number;
      bbox?: [number, number, number, number];
    }>;
  };
}

export default function DamageInfo({ damage }: DamageInfoProps) {
  if (!damage) {
    return (
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6">
        <h3 className="text-lg font-semibold mb-4 text-slate-900">Damage Assessment</h3>
        <p className="text-slate-500">No damage data available</p>
      </div>
    );
  }

  const scratchesCount = damage.scratches?.count || 0;
  const dentsCount = damage.dents?.count || 0;
  const rustCount = damage.rust?.count || 0;
  const severity = damage.severity || "low";
  const totalDamage = scratchesCount + dentsCount + rustCount;

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 hover:shadow-md transition-shadow">
      <h3 className="text-lg font-semibold mb-4 text-slate-900">Damage Assessment</h3>
      <div className="space-y-4">
        {/* Severity badge */}
        <div>
          <span className="text-sm text-slate-600">Overall Severity:</span>
          <span
            className={`ml-2 px-3 py-1 rounded-full text-sm font-medium ${
              severity === "high"
                ? "bg-red-100 text-red-800"
                : severity === "medium"
                ? "bg-yellow-100 text-yellow-800"
                : "bg-green-100 text-green-800"
            }`}
          >
            {severity.toUpperCase()}
          </span>
        </div>

        {/* Damage counts */}
        <div className="grid grid-cols-3 gap-4">
          <div className="text-center p-4 bg-slate-50 rounded-lg border border-slate-200">
            <div className="text-2xl font-bold text-slate-900">
              {scratchesCount}
            </div>
            <div className="text-sm text-slate-600 mt-1">Scratches</div>
          </div>
          <div className="text-center p-4 bg-slate-50 rounded-lg border border-slate-200">
            <div className="text-2xl font-bold text-slate-900">{dentsCount}</div>
            <div className="text-sm text-slate-600 mt-1">Dents</div>
          </div>
          <div className="text-center p-4 bg-slate-50 rounded-lg border border-slate-200">
            <div className="text-2xl font-bold text-slate-900">{rustCount}</div>
            <div className="text-sm text-slate-600 mt-1">Rust Areas</div>
          </div>
        </div>

        {/* Summary */}
        {totalDamage === 0 && (
          <div className="p-4 bg-green-50 rounded-lg border border-green-200">
            <p className="text-green-800 font-medium">
              ✓ No significant damage detected
            </p>
          </div>
        )}
        {totalDamage > 0 && (
          <div className="p-4 bg-yellow-50 rounded-lg border border-yellow-200">
            <p className="text-yellow-800 font-medium">
              Total damage areas detected: {totalDamage}
            </p>
          </div>
        )}

        {/* Damage snapshots */}
        {damage.locations && damage.locations.length > 0 && (
          <div className="mt-6">
            <h4 className="text-sm font-semibold text-slate-700 mb-3">
              Damage Snapshots
              {damage.locations.filter((loc) => loc.snapshot && (loc.confidence || 0) >= 0.3).length > 0 && (
                <span className="text-xs text-slate-500 font-normal ml-2">
                  ({damage.locations.filter((loc) => loc.snapshot && (loc.confidence || 0) >= 0.3).length} high-confidence detections)
                </span>
              )}
            </h4>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              {damage.locations
                .filter((loc) => loc.snapshot && (loc.confidence || 0) >= 0.3) // Only show detections with >= 30% confidence
                .slice(0, 9)
                .map((location, idx) => {
                  const snapshotUrl = location.snapshot
                    ? `${BACKEND_BASE_URL}/${location.snapshot}`
                    : null;
                  
                  if (!snapshotUrl) return null;

                  const confidence = location.confidence || 0;
                  const confidencePercent = Math.round(confidence * 100);

                  const damageTypeColors = {
                    scratch: "border-yellow-300 bg-yellow-50",
                    dent: "border-orange-300 bg-orange-50",
                    rust: "border-red-300 bg-red-50",
                  };

                  const typeColor =
                    damageTypeColors[
                      location.type?.toLowerCase() as keyof typeof damageTypeColors
                    ] || "border-slate-300 bg-slate-50";

                  // Confidence badge color
                  const confidenceColor =
                    confidence >= 0.7
                      ? "bg-green-500"
                      : confidence >= 0.5
                      ? "bg-yellow-500"
                      : "bg-orange-500";

                  return (
                    <div
                      key={idx}
                      className={`relative rounded-lg border-2 overflow-hidden ${typeColor} group cursor-pointer hover:shadow-lg transition-shadow`}
                    >
                      <div className="aspect-square relative">
                        <Image
                          src={snapshotUrl}
                          alt={`${location.type} damage ${idx + 1}`}
                          fill
                          className="object-cover"
                          sizes="(max-width: 768px) 50vw, 33vw"
                        />
                        {/* Confidence badge */}
                        {confidence >= 0.3 && (
                          <div className="absolute top-2 right-2">
                            <div className={`${confidenceColor} text-white text-xs font-semibold px-2 py-1 rounded-full shadow-lg`}>
                              {confidencePercent}%
                            </div>
                          </div>
                        )}
                      </div>
                      <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/80 to-black/60 text-white text-xs px-2 py-2">
                        <div className="font-semibold capitalize">{location.type}</div>
                        {confidence >= 0.5 && (
                          <div className="text-xs opacity-90 mt-0.5">
                            High confidence detection
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
            </div>
            {damage.locations.filter((loc) => loc.snapshot && (loc.confidence || 0) >= 0.3).length === 0 && (
              <div className="text-center py-6">
                <p className="text-sm text-slate-500 italic">
                  No high-confidence damage snapshots available
                </p>
                {damage.locations.filter((loc) => loc.snapshot).length > 0 && (
                  <p className="text-xs text-slate-400 mt-1">
                    ({damage.locations.filter((loc) => loc.snapshot).length} low-confidence detections filtered out)
                  </p>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
