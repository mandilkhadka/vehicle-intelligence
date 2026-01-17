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
    confidence?: number;
  };
}

export default function VehicleInfo({ vehicleInfo }: VehicleInfoProps) {
  if (!vehicleInfo) {
    return (
      <div className="bg-white rounded-lg shadow p-6">
        <h3 className="text-lg font-semibold mb-4">Vehicle Information</h3>
        <p className="text-gray-500">No vehicle information available</p>
      </div>
    );
  }

  const confidencePercent = vehicleInfo.confidence
    ? Math.round(vehicleInfo.confidence * 100)
    : 0;

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <h3 className="text-lg font-semibold mb-4">Vehicle Information</h3>
      <div className="space-y-3">
        <div>
          <span className="text-sm text-gray-600">Type:</span>
          <span className="ml-2 font-medium capitalize">
            {vehicleInfo.type || "Unknown"}
          </span>
        </div>
        <div>
          <span className="text-sm text-gray-600">Brand:</span>
          <span className="ml-2 font-medium">
            {vehicleInfo.brand || "Unknown"}
          </span>
        </div>
        <div>
          <span className="text-sm text-gray-600">Model:</span>
          <span className="ml-2 font-medium">
            {vehicleInfo.model || "Unknown"}
          </span>
        </div>
        <div>
          <span className="text-sm text-gray-600">Confidence:</span>
          <span className="ml-2 font-medium">{confidencePercent}%</span>
          <div className="mt-1 w-full bg-gray-200 rounded-full h-2">
            <div
              className="bg-blue-600 h-2 rounded-full"
              style={{ width: `${confidencePercent}%` }}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
