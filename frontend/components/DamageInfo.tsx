"use client";

/**
 * Damage information display component
 * Shows detected damage (scratches, dents, rust) and severity
 */

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
  };
}

export default function DamageInfo({ damage }: DamageInfoProps) {
  if (!damage) {
    return (
      <div className="bg-white rounded-lg shadow p-6">
        <h3 className="text-lg font-semibold mb-4">Damage Assessment</h3>
        <p className="text-gray-500">No damage data available</p>
      </div>
    );
  }

  const scratchesCount = damage.scratches?.count || 0;
  const dentsCount = damage.dents?.count || 0;
  const rustCount = damage.rust?.count || 0;
  const severity = damage.severity || "low";
  const totalDamage = scratchesCount + dentsCount + rustCount;

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <h3 className="text-lg font-semibold mb-4">Damage Assessment</h3>
      <div className="space-y-4">
        {/* Severity badge */}
        <div>
          <span className="text-sm text-gray-600">Overall Severity:</span>
          <span
            className={`ml-2 px-3 py-1 rounded-full text-sm font-medium ${
              severity === "high"
                ? "bg-red-100 text-red-800"
                : "bg-yellow-100 text-yellow-800"
            }`}
          >
            {severity.toUpperCase()}
          </span>
        </div>

        {/* Damage counts */}
        <div className="grid grid-cols-3 gap-4">
          <div className="text-center p-4 bg-gray-50 rounded-lg">
            <div className="text-2xl font-bold text-gray-900">
              {scratchesCount}
            </div>
            <div className="text-sm text-gray-600 mt-1">Scratches</div>
          </div>
          <div className="text-center p-4 bg-gray-50 rounded-lg">
            <div className="text-2xl font-bold text-gray-900">{dentsCount}</div>
            <div className="text-sm text-gray-600 mt-1">Dents</div>
          </div>
          <div className="text-center p-4 bg-gray-50 rounded-lg">
            <div className="text-2xl font-bold text-gray-900">{rustCount}</div>
            <div className="text-sm text-gray-600 mt-1">Rust Areas</div>
          </div>
        </div>

        {/* Summary */}
        {totalDamage === 0 && (
          <div className="p-4 bg-green-50 rounded-lg">
            <p className="text-green-800 font-medium">
              No significant damage detected
            </p>
          </div>
        )}
        {totalDamage > 0 && (
          <div className="p-4 bg-yellow-50 rounded-lg">
            <p className="text-yellow-800">
              Total damage areas detected: {totalDamage}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
