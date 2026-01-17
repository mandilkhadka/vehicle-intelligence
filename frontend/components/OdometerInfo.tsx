"use client";

/**
 * Odometer information display component
 * Shows odometer reading and speedometer image
 */

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
      <div className="bg-white rounded-lg shadow p-6">
        <h3 className="text-lg font-semibold mb-4">Odometer Reading</h3>
        <p className="text-gray-500">No odometer data available</p>
      </div>
    );
  }

  const confidencePercent = odometer.confidence
    ? Math.round(odometer.confidence * 100)
    : 0;

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <h3 className="text-lg font-semibold mb-4">Odometer Reading</h3>
      <div className="space-y-4">
        <div>
          <span className="text-sm text-gray-600">Value:</span>
          <span className="ml-2 text-2xl font-bold">
            {odometer.value !== null && odometer.value !== undefined
              ? `${odometer.value.toLocaleString()} km`
              : "Not detected"}
          </span>
        </div>
        <div>
          <span className="text-sm text-gray-600">Confidence:</span>
          <span className="ml-2 font-medium">{confidencePercent}%</span>
          <div className="mt-1 w-full bg-gray-200 rounded-full h-2">
            <div
              className="bg-green-600 h-2 rounded-full"
              style={{ width: `${confidencePercent}%` }}
            />
          </div>
        </div>
        {odometer.speedometer_image_path && (
          <div>
            <span className="text-sm text-gray-600 block mb-2">
              Speedometer Image:
            </span>
            <img
              src={`http://localhost:3001/uploads/${odometer.speedometer_image_path.replace(/^.*uploads\//, "")}`}
              alt="Speedometer"
              className="max-w-full h-auto rounded-lg border border-gray-200"
              onError={(e) => {
                (e.target as HTMLImageElement).style.display = "none";
              }}
            />
          </div>
        )}
      </div>
    </div>
  );
}
