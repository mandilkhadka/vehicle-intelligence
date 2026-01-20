"use client";

/**
 * Inspection results page
 * Displays complete inspection data including all findings
 */

import { useState, useEffect } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import Image from "next/image";
import { Car } from "lucide-react";
import { getInspection, BACKEND_BASE_URL } from "@/lib/api";
import VehicleInfo from "@/components/VehicleInfo";
import OdometerInfo from "@/components/OdometerInfo";
import DamageInfo from "@/components/DamageInfo";
import ExhaustInfo from "@/components/ExhaustInfo";

export default function InspectionPage() {
  const params = useParams();
  const inspectionId = params.id as string;
  const [inspection, setInspection] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchInspection = async () => {
      try {
        const data = await getInspection(inspectionId);
        setInspection(data);
      } catch (err: any) {
        setError("Failed to load inspection data");
        console.error(err);
      } finally {
        setLoading(false);
      }
    };

    if (inspectionId) {
      fetchInspection();
    }
  }, [inspectionId]);

  /**
   * Download inspection report as JSON
   */
  const downloadReport = () => {
    if (!inspection) return;

    const dataStr = JSON.stringify(inspection, null, 2);
    const dataBlob = new Blob([dataStr], { type: "application/json" });
    const url = URL.createObjectURL(dataBlob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `inspection-${inspectionId}.json`;
    link.click();
    URL.revokeObjectURL(url);
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-[#f8fafc] flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
          <p className="mt-4 text-slate-600 font-medium">Loading inspection data...</p>
        </div>
      </div>
    );
  }

  if (error || !inspection) {
    return (
      <div className="min-h-screen bg-[#f8fafc] flex items-center justify-center">
        <div className="text-center">
          <p className="text-red-600 mb-4 font-medium">{error || "Inspection not found"}</p>
          <Link
            href="/"
            className="text-blue-600 hover:text-blue-700 font-medium transition-colors"
          >
            Go back home
          </Link>
        </div>
      </div>
    );
  }

  // Parse JSON fields if they're strings
  const vehicleInfo =
    typeof inspection.vehicle_info === "string"
      ? JSON.parse(inspection.vehicle_info)
      : inspection.vehicle_info || {
          type: inspection.vehicle_type,
          brand: inspection.vehicle_brand,
          model: inspection.vehicle_model,
          confidence: inspection.vehicle_confidence,
        };

  const odometer = {
    value: inspection.odometer_value,
    confidence: inspection.odometer_confidence,
    speedometer_image_path: inspection.speedometer_image_path,
  };

  const damage =
    typeof inspection.damage_summary === "string"
      ? JSON.parse(inspection.damage_summary)
      : inspection.damage_summary || {
          scratches: { count: inspection.scratches_detected || 0 },
          dents: { count: inspection.dents_detected || 0 },
          rust: { count: inspection.rust_detected || 0 },
          severity: inspection.damage_severity || "low",
        };

  const exhaust = {
    type: inspection.exhaust_type,
    confidence: inspection.exhaust_confidence,
    exhaust_image_path: inspection.exhaust_image_path,
  };

  const report =
    typeof inspection.inspection_report === "string"
      ? JSON.parse(inspection.inspection_report)
      : inspection.inspection_report;

  const frames =
    typeof inspection.extracted_frames === "string"
      ? JSON.parse(inspection.extracted_frames)
      : inspection.extracted_frames || [];

  return (
    <div className="min-h-screen bg-[#f8fafc]">
      <nav className="border-b border-slate-200 bg-white/80 backdrop-blur-xl">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between h-16">
            <div className="flex items-center gap-2">
              <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-600">
                <Car className="h-5 w-5 text-white" />
              </div>
              <Link href="/" className="text-xl font-semibold text-slate-900">
                Vehicle Intelligence Platform
              </Link>
            </div>
            <div className="flex items-center space-x-4">
              <button
                onClick={downloadReport}
                className="bg-blue-600 text-white hover:bg-blue-700 px-4 py-2 rounded-lg text-sm font-medium shadow-sm transition-colors"
              >
                Download JSON
              </button>
              <Link
                href="/"
                className="text-sm font-medium text-slate-700 hover:text-blue-600 transition-colors px-3 py-2 rounded-md"
              >
                Home
              </Link>
            </div>
          </div>
        </div>
      </nav>

      <main className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
        <div className="px-4 py-6">
          <h1 className="text-3xl font-bold mb-6 text-slate-900">Inspection Results</h1>

          {/* Summary Report */}
          {report && (
            <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 mb-6">
              <h2 className="text-xl font-semibold mb-4 text-slate-900">Summary</h2>
              <p className="text-slate-700 leading-relaxed">{report.summary}</p>
              {report.recommendations && report.recommendations.length > 0 && (
                <div className="mt-4">
                  <h3 className="font-semibold mb-2 text-slate-800">Recommendations:</h3>
                  <ul className="list-disc list-inside space-y-1 text-slate-700">
                    {report.recommendations.map((rec: string, idx: number) => (
                      <li key={idx}>{rec}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          {/* Grid layout for components */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
            <VehicleInfo vehicleInfo={vehicleInfo} />
            <OdometerInfo odometer={odometer} />
            <DamageInfo damage={damage} />
            <ExhaustInfo exhaust={exhaust} />
          </div>

          {/* Frame Gallery */}
          {frames && frames.length > 0 && (
            <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6">
              <h2 className="text-xl font-semibold mb-4 text-slate-900">Extracted Frames</h2>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {frames.slice(0, 12).map((frame: string, idx: number) => {
                  // Handle both relative and absolute paths
                  const framePath = frame.startsWith("uploads/")
                    ? frame
                    : `uploads/${frame.replace(/^.*uploads\//, "")}`;
                  return (
                    <div key={idx} className="relative aspect-video rounded-lg border border-slate-200 overflow-hidden shadow-sm hover:shadow-md transition-shadow">
                      <Image
                        src={`${BACKEND_BASE_URL}/${framePath}`}
                        alt={`Frame ${idx + 1}`}
                        fill
                        className="object-cover"
                        unoptimized
                      />
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
