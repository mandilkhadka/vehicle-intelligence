"use client";

/**
 * Exhaust information display component
 * Shows exhaust type (stock/modified) and confidence
 */

interface ExhaustInfoProps {
  exhaust?: {
    type?: string;
    confidence?: number;
  };
}

export default function ExhaustInfo({ exhaust }: ExhaustInfoProps) {
  if (!exhaust) {
    return (
      <div className="bg-white rounded-lg shadow p-6">
        <h3 className="text-lg font-semibold mb-4">Exhaust System</h3>
        <p className="text-gray-500">No exhaust data available</p>
      </div>
    );
  }

  const confidencePercent = exhaust.confidence
    ? Math.round(exhaust.confidence * 100)
    : 0;
  const isModified = exhaust.type === "modified";

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <h3 className="text-lg font-semibold mb-4">Exhaust System</h3>
      <div className="space-y-3">
        <div>
          <span className="text-sm text-gray-600">Type:</span>
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
          <span className="text-sm text-gray-600">Confidence:</span>
          <span className="ml-2 font-medium">{confidencePercent}%</span>
          <div className="mt-1 w-full bg-gray-200 rounded-full h-2">
            <div
              className={`h-2 rounded-full ${
                isModified ? "bg-orange-600" : "bg-green-600"
              }`}
              style={{ width: `${confidencePercent}%` }}
            />
          </div>
        </div>
        {isModified && (
          <div className="p-3 bg-orange-50 rounded-lg">
            <p className="text-sm text-orange-800">
              Modified exhaust detected. Please verify compliance with local
              regulations.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
