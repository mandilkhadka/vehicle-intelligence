"use client";

/**
 * Odometer information display component
 * Shows odometer reading and speedometer image
 */

import Image from "next/image";
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
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6">
        <h3 className="text-lg font-semibold mb-4 text-slate-900">Odometer Reading</h3>
        <p className="text-slate-500">No odometer data available</p>
      </div>
    );
  }

  const confidencePercent = odometer.confidence
    ? Math.round(odometer.confidence * 100)
    : 0;

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 hover:shadow-md transition-shadow">
      <h3 className="text-lg font-semibold mb-4 text-slate-900">Odometer Reading</h3>
      <div className="space-y-4">
        <div>
          <span className="text-sm text-slate-600">Value:</span>
          <span className="ml-2 text-2xl font-bold text-slate-900">
            {odometer.value !== null && odometer.value !== undefined
              ? `${odometer.value.toLocaleString()} km`
              : "Not detected"}
          </span>
        </div>
        <div>
          <span className="text-sm text-slate-600">Confidence:</span>
          <span className="ml-2 font-medium text-green-600">{confidencePercent}%</span>
          <div className="mt-1 w-full bg-slate-200 rounded-full h-2">
            <div
              className="bg-green-600 h-2 rounded-full transition-all"
              style={{ width: `${confidencePercent}%` }}
            />
          </div>
        </div>
        {odometer.speedometer_image_path && (
          <div>
            <span className="text-sm text-slate-600 block mb-2">
              Speedometer Image:
            </span>
            <div className="relative w-full aspect-video rounded-lg border border-slate-200 overflow-hidden bg-slate-50">
              <Image
                src={`${BACKEND_BASE_URL}/uploads/${odometer.speedometer_image_path.replace(/^.*uploads\//, "")}`}
                alt="Speedometer"
                fill
                className="object-contain"
                unoptimized
              />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
