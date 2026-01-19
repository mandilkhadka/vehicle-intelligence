"use client";

/**
 * Upload guide component
 * Provides visual instructions for taking videos and photos
 */

import { useState } from "react";
import { Camera, Video, ZoomIn, CheckCircle } from "lucide-react";

export default function UploadGuide() {
  const [expandedSection, setExpandedSection] = useState<string | null>(null);

  const toggleSection = (section: string) => {
    setExpandedSection(expandedSection === section ? null : section);
  };

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 mb-6">
      <h2 className="text-2xl font-bold mb-6 text-slate-900 flex items-center gap-2">
        <Camera className="h-6 w-6 text-blue-600" />
        How to Capture Your Vehicle Inspection
      </h2>

      {/* Video Recording Guide */}
      <div className="mb-6">
        <button
          onClick={() => toggleSection("video")}
          className="w-full flex items-center justify-between p-4 bg-slate-50 rounded-lg hover:bg-slate-100 transition-colors"
        >
          <div className="flex items-center gap-3">
            <Video className="h-5 w-5 text-blue-600" />
            <span className="font-semibold text-slate-900">Video Recording Guide</span>
          </div>
          <span className="text-slate-500">
            {expandedSection === "video" ? "−" : "+"}
          </span>
        </button>

        {expandedSection === "video" && (
          <div className="mt-4 p-4 bg-blue-50 rounded-lg border border-blue-200">
            <div className="space-y-4">
              <div className="flex items-start gap-3">
                <CheckCircle className="h-5 w-5 text-green-600 mt-0.5 flex-shrink-0" />
                <div>
                  <p className="font-medium text-slate-900">Walk around the vehicle</p>
                  <p className="text-sm text-slate-600 mt-1">
                    Record a complete 360° walkaround video, moving slowly around the entire vehicle
                  </p>
                </div>
              </div>

              <div className="flex items-start gap-3">
                <CheckCircle className="h-5 w-5 text-green-600 mt-0.5 flex-shrink-0" />
                <div>
                  <p className="font-medium text-slate-900">Keep camera steady</p>
                  <p className="text-sm text-slate-600 mt-1">
                    Hold your phone/camera steady and move slowly. Avoid shaking or rapid movements
                  </p>
                </div>
              </div>

              <div className="flex items-start gap-3">
                <CheckCircle className="h-5 w-5 text-green-600 mt-0.5 flex-shrink-0" />
                <div>
                  <p className="font-medium text-slate-900">Good lighting</p>
                  <p className="text-sm text-slate-600 mt-1">
                    Record in daylight or well-lit area. Avoid shadows and glare
                  </p>
                </div>
              </div>

              <div className="flex items-start gap-3">
                <CheckCircle className="h-5 w-5 text-green-600 mt-0.5 flex-shrink-0" />
                <div>
                  <p className="font-medium text-slate-900">Include all angles</p>
                  <p className="text-sm text-slate-600 mt-1">
                    Capture front, back, sides, roof, and wheels. Include interior dashboard if possible
                  </p>
                </div>
              </div>

              <div className="mt-4 p-3 bg-white rounded border border-blue-300">
                <p className="text-sm font-medium text-blue-900 mb-2">📹 Video Tips:</p>
                <ul className="text-sm text-slate-700 space-y-1 list-disc list-inside">
                  <li>Record in landscape (horizontal) mode</li>
                  <li>Duration: 30-60 seconds is ideal</li>
                  <li>Keep vehicle centered in frame</li>
                  <li>Start recording before approaching the vehicle</li>
                </ul>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Odometer Photo Guide */}
      <div className="mb-6">
        <button
          onClick={() => toggleSection("odometer")}
          className="w-full flex items-center justify-between p-4 bg-slate-50 rounded-lg hover:bg-slate-100 transition-colors"
        >
          <div className="flex items-center gap-3">
            <Camera className="h-5 w-5 text-blue-600" />
            <span className="font-semibold text-slate-900">Odometer Photo Guide</span>
            <span className="text-xs bg-blue-100 text-blue-700 px-2 py-1 rounded">Optional</span>
          </div>
          <span className="text-slate-500">
            {expandedSection === "odometer" ? "−" : "+"}
          </span>
        </button>

        {expandedSection === "odometer" && (
          <div className="mt-4 p-4 bg-green-50 rounded-lg border border-green-200">
            <div className="space-y-4">
              <div className="flex items-start gap-3">
                <CheckCircle className="h-5 w-5 text-green-600 mt-0.5 flex-shrink-0" />
                <div>
                  <p className="font-medium text-slate-900">Take a clear close-up photo</p>
                  <p className="text-sm text-slate-600 mt-1">
                    Position your camera directly in front of the odometer display
                  </p>
                </div>
              </div>

              <div className="flex items-start gap-3">
                <CheckCircle className="h-5 w-5 text-green-600 mt-0.5 flex-shrink-0" />
                <div>
                  <p className="font-medium text-slate-900">Ensure good visibility</p>
                  <p className="text-sm text-slate-600 mt-1">
                    Make sure the odometer numbers are clearly visible and in focus
                  </p>
                </div>
              </div>

              <div className="flex items-start gap-3">
                <CheckCircle className="h-5 w-5 text-green-600 mt-0.5 flex-shrink-0" />
                <div>
                  <p className="font-medium text-slate-900">Avoid glare</p>
                  <p className="text-sm text-slate-600 mt-1">
                    Position yourself to avoid reflections on the dashboard glass
                  </p>
                </div>
              </div>

              <div className="mt-4 p-3 bg-white rounded border border-green-300">
                <p className="text-sm font-medium text-green-900 mb-2">📸 Photo Tips:</p>
                <ul className="text-sm text-slate-700 space-y-1 list-disc list-inside">
                  <li>Hold camera steady to avoid blur</li>
                  <li>Fill the frame with the odometer display</li>
                  <li>Use flash if needed, but avoid direct glare</li>
                  <li>Take multiple photos if unsure about clarity</li>
                </ul>
              </div>

              <div className="mt-4 p-3 bg-yellow-50 border border-yellow-200 rounded">
                <p className="text-sm text-yellow-800">
                  <strong>Note:</strong> If you don't upload an odometer photo, our AI will attempt to read it from the video. A clear photo improves accuracy significantly.
                </p>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Damage Close-up Guide */}
      <div>
        <button
          onClick={() => toggleSection("damage")}
          className="w-full flex items-center justify-between p-4 bg-slate-50 rounded-lg hover:bg-slate-100 transition-colors"
        >
          <div className="flex items-center gap-3">
            <ZoomIn className="h-5 w-5 text-blue-600" />
            <span className="font-semibold text-slate-900">Damage Close-up Guide</span>
          </div>
          <span className="text-slate-500">
            {expandedSection === "damage" ? "−" : "+"}
          </span>
        </button>

        {expandedSection === "damage" && (
          <div className="mt-4 p-4 bg-orange-50 rounded-lg border border-orange-200">
            <div className="space-y-4">
              <div className="flex items-start gap-3">
                <CheckCircle className="h-5 w-5 text-orange-600 mt-0.5 flex-shrink-0" />
                <div>
                  <p className="font-medium text-slate-900">Zoom in on damage areas</p>
                  <p className="text-sm text-slate-600 mt-1">
                    When you see scratches, dents, or rust, pause and zoom in for 2-3 seconds
                  </p>
                </div>
              </div>

              <div className="flex items-start gap-3">
                <CheckCircle className="h-5 w-5 text-orange-600 mt-0.5 flex-shrink-0" />
                <div>
                  <p className="font-medium text-slate-900">Capture multiple angles</p>
                  <p className="text-sm text-slate-600 mt-1">
                    Show damage from different angles - front, side, and close-up
                  </p>
                </div>
              </div>

              <div className="flex items-start gap-3">
                <CheckCircle className="h-5 w-5 text-orange-600 mt-0.5 flex-shrink-0" />
                <div>
                  <p className="font-medium text-slate-900">Show scale</p>
                  <p className="text-sm text-slate-600 mt-1">
                    Include surrounding area to show size relative to vehicle
                  </p>
                </div>
              </div>

              <div className="mt-4 p-3 bg-white rounded border border-orange-300">
                <p className="text-sm font-medium text-orange-900 mb-2">🔍 Close-up Tips:</p>
                <ul className="text-sm text-slate-700 space-y-1 list-disc list-inside">
                  <li>Pause and zoom in when you spot damage</li>
                  <li>Hold steady for 2-3 seconds on each damage area</li>
                  <li>Move camera closer rather than using digital zoom if possible</li>
                  <li>Ensure good lighting on the damaged area</li>
                  <li>Show the full extent of scratches or dents</li>
                </ul>
              </div>

              <div className="grid grid-cols-2 gap-3 mt-4">
                <div className="p-3 bg-white rounded border border-orange-200">
                  <p className="text-xs font-semibold text-slate-900 mb-1">✅ Good Close-up</p>
                  <p className="text-xs text-slate-600">
                    Clear, focused, shows full damage area with context
                  </p>
                </div>
                <div className="p-3 bg-white rounded border border-orange-200">
                  <p className="text-xs font-semibold text-slate-900 mb-1">❌ Poor Close-up</p>
                  <p className="text-xs text-slate-600">
                    Blurry, too far away, or missing context
                  </p>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Quick Summary */}
      <div className="mt-6 p-4 bg-blue-50 rounded-lg border border-blue-200">
        <p className="text-sm font-semibold text-blue-900 mb-2">📋 Quick Checklist:</p>
        <ul className="text-sm text-slate-700 space-y-1">
          <li>✓ Complete 360° walkaround video</li>
          <li>✓ Optional: Clear odometer photo</li>
          <li>✓ Zoom in on any visible damage</li>
          <li>✓ Good lighting throughout</li>
          <li>✓ Steady camera movements</li>
        </ul>
      </div>
    </div>
  );
}
