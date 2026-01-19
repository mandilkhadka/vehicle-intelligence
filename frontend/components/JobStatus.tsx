"use client";

/**
 * Job status component
 * Displays job processing status and redirects to results when complete
 */

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { getJobStatus } from "@/lib/api";

interface JobStatusProps {
  jobId: string;
}

export default function JobStatus({ jobId }: JobStatusProps) {
  const [status, setStatus] = useState<string>("pending");
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();

  /**
   * Poll job status
   */
  useEffect(() => {
    const pollStatus = async () => {
      try {
        const jobData = await getJobStatus(jobId);
        setStatus(jobData.status);
        setProgress(jobData.progress || 0);

        if (jobData.status === "completed" && (jobData.inspectionId || jobData.inspection_id)) {
          // Redirect to inspection results
          setTimeout(() => {
            router.push(`/inspection/${jobData.inspectionId || jobData.inspection_id}`);
          }, 1000);
        } else if (jobData.status === "failed") {
          setError(jobData.error_message || jobData.error || "Processing failed");
        }
      } catch (err: any) {
        setError("Failed to fetch job status");
        console.error(err);
      }
    };

    // Poll immediately
    pollStatus();

    // Poll every 2 seconds if not completed or failed
    const interval = setInterval(() => {
      if (status !== "completed" && status !== "failed") {
        pollStatus();
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [jobId, status, router]);

  return (
    <div className="max-w-2xl mx-auto p-6">
      <h2 className="text-2xl font-bold mb-6 text-slate-900">Processing Video</h2>

      {/* Status display */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6">
        <div className="mb-4">
          <div className="flex justify-between text-sm text-slate-700 mb-2 font-medium">
            <span className="capitalize">Status: <span className="font-bold">{status}</span></span>
            <span className="font-bold text-blue-600">{progress}%</span>
          </div>
          <div className="w-full bg-slate-200 rounded-full h-3">
            <div
              className={`h-3 rounded-full transition-all duration-300 ${
                status === "failed"
                  ? "bg-red-600"
                  : status === "completed"
                  ? "bg-green-600"
                  : "bg-blue-600"
              }`}
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>

        {/* Status messages */}
        {status === "pending" && (
          <p className="text-slate-600 font-medium">Job is queued and waiting to start...</p>
        )}
        {status === "processing" && (
          <div>
            <p className="text-slate-700 mb-3 font-semibold">Processing video...</p>
            <ul className="text-sm text-slate-600 space-y-2">
              <li className="flex items-center gap-2">
                <span className="text-green-500">✓</span> Extracting frames
              </li>
              <li className="flex items-center gap-2">
                <span className="text-blue-500 animate-pulse">⏳</span> Identifying vehicle
              </li>
              <li className="flex items-center gap-2">
                <span className="text-blue-500 animate-pulse">⏳</span> Reading odometer
              </li>
              <li className="flex items-center gap-2">
                <span className="text-blue-500 animate-pulse">⏳</span> Detecting damage
              </li>
              <li className="flex items-center gap-2">
                <span className="text-blue-500 animate-pulse">⏳</span> Classifying exhaust
              </li>
              <li className="flex items-center gap-2">
                <span className="text-blue-500 animate-pulse">⏳</span> Generating report
              </li>
            </ul>
          </div>
        )}
        {status === "completed" && (
          <div className="text-green-600">
            <p className="font-bold text-lg">Processing complete! 🎉</p>
            <p className="text-sm mt-1">Redirecting to results...</p>
          </div>
        )}
        {status === "failed" && (
          <div className="text-red-600">
            <p className="font-bold text-lg">Processing failed</p>
            {error && error !== "Processing failed" && (
              <p className="text-sm mt-1">{error}</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
