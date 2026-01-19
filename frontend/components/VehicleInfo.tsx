"use client";

/**
 * Vehicle information display component
 * Shows vehicle type, brand, model, and confidence score
 */

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
  if (!vehicleInfo) {
    return (
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6">
        <h3 className="text-lg font-semibold mb-4 text-slate-900">Vehicle Information</h3>
        <p className="text-slate-500">No vehicle information available</p>
      </div>
    );
  }

  const confidencePercent = vehicleInfo.confidence
    ? Math.round(vehicleInfo.confidence * 100)
    : 0;

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 hover:shadow-md transition-shadow">
      <h3 className="text-lg font-semibold mb-4 text-slate-900">Vehicle Information</h3>
      <div className="space-y-3">
        <div>
          <span className="text-sm text-slate-600">Type:</span>
          <span className="ml-2 font-medium text-slate-900 capitalize">
            {vehicleInfo.type || "Unknown"}
          </span>
        </div>
        <div>
          <span className="text-sm text-slate-600">Brand:</span>
          <span className="ml-2 font-medium text-slate-900">
            {vehicleInfo.brand || "Unknown"}
          </span>
        </div>
        <div>
          <span className="text-sm text-slate-600">Model:</span>
          <span className="ml-2 font-medium text-slate-900">
            {vehicleInfo.model || "Unknown"}
          </span>
        </div>
        {vehicleInfo.color && (
          <div>
            <span className="text-sm text-slate-600">Color:</span>
            <span className="ml-2 font-medium text-slate-900 capitalize">
              {vehicleInfo.color}
            </span>
          </div>
        )}
        <div>
          <span className="text-sm text-slate-600">Confidence:</span>
          <span className="ml-2 font-medium text-blue-600">{confidencePercent}%</span>
          <div className="mt-1 w-full bg-slate-200 rounded-full h-2">
            <div
              className="bg-blue-600 h-2 rounded-full transition-all"
              style={{ width: `${confidencePercent}%` }}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
