"use client";

/**
 * Exhaust information display component
 * Shows exhaust type (stock/modified) and confidence
 */

import { BACKEND_BASE_URL } from "@/lib/api";
import Image from "next/image";

interface ExhaustInfoProps {
  exhaust?: {
    type?: string;
    confidence?: number;
    exhaust_image_path?: string;
  };
}

export default function ExhaustInfo({ exhaust }: ExhaustInfoProps) {
  if (!exhaust) {
    return (
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6">
        <h3 className="text-lg font-semibold mb-4 text-slate-900">Exhaust System</h3>
        <p className="text-slate-500">No exhaust data available</p>
      </div>
    );
  }

  const confidencePercent = exhaust.confidence
    ? Math.round(exhaust.confidence * 100)
    : 0;
  const isModified = exhaust.type === "modified";

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 hover:shadow-md transition-shadow">
      <h3 className="text-lg font-semibold mb-4 text-slate-900">Exhaust System</h3>
      <div className="space-y-3">
        <div>
          <span className="text-sm text-slate-600">Type:</span>
          <span
            className={`ml-2 px-3 py-1 rounded-full text-sm font-medium ${
              isModified
                ? "bg-orange-100 text-orange-800"
                : "bg-green-100 text-green-800"
            }`}
          >
            {exhaust.type ? exhaust.type.toUpperCase() : "Unknown"}
          </span>
        </div>
        <div>
          <span className="text-sm text-slate-600">Confidence:</span>
          <span className="ml-2 font-medium text-blue-600">{confidencePercent}%</span>
          <div className="mt-1 w-full bg-slate-200 rounded-full h-2">
            <div
              className={`h-2 rounded-full transition-all ${
                isModified ? "bg-orange-600" : "bg-green-600"
              }`}
              style={{ width: `${confidencePercent}%` }}
            />
          </div>
        </div>
        {isModified && (
          <div className="p-3 bg-orange-50 rounded-lg border border-orange-200">
            <p className="text-sm text-orange-800">
              ⚠️ Modified exhaust detected. Please verify compliance with local regulations.
            </p>
          </div>
        )}

        {/* Exhaust Image */}
        {exhaust.exhaust_image_path && (
          <div className="mt-4">
            <h4 className="text-sm font-semibold text-slate-700 mb-3">Exhaust Image</h4>
            <div className="relative aspect-video rounded-lg border border-slate-200 overflow-hidden shadow-sm hover:shadow-md transition-shadow bg-slate-50">
              <Image
                src={`${BACKEND_BASE_URL}/${exhaust.exhaust_image_path}`}
                alt="Exhaust system"
                fill
                className="object-cover"
                sizes="(max-width: 768px) 100vw, 50vw"
                unoptimized
              />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
