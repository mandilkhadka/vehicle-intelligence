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

        if (jobData.status === "completed" && jobData.inspectionId) {
          // Redirect to inspection results
          setTimeout(() => {
            router.push(`/inspection/${jobData.inspectionId}`);
          }, 1000);
        } else if (jobData.status === "failed") {
          setError(jobData.error || "Processing failed");
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
      <h2 className="text-2xl font-bold mb-6">Processing Video</h2>

      {/* Status display */}
      <div className="bg-white rounded-lg shadow p-6">
        <div className="mb-4">
          <div className="flex justify-between text-sm text-gray-600 mb-2">
            <span>Status: {status}</span>
            <span>{progress}%</span>
          </div>
          <div className="w-full bg-gray-200 rounded-full h-3">
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
          <p className="text-gray-600">Job is queued and waiting to start...</p>
        )}
        {status === "processing" && (
          <div>
            <p className="text-gray-600 mb-2">Processing video...</p>
            <ul className="text-sm text-gray-500 space-y-1">
              <li>✓ Extracting frames</li>
              <li>⏳ Identifying vehicle</li>
              <li>⏳ Reading odometer</li>
              <li>⏳ Detecting damage</li>
              <li>⏳ Classifying exhaust</li>
              <li>⏳ Generating report</li>
            </ul>
          </div>
        )}
        {status === "completed" && (
          <div className="text-green-600">
            <p className="font-medium">Processing complete!</p>
            <p className="text-sm mt-1">Redirecting to results...</p>
          </div>
        )}
        {status === "failed" && error && (
          <div className="text-red-600">
            <p className="font-medium">Processing failed</p>
            <p className="text-sm mt-1">{error}</p>
          </div>
        )}
      </div>
    </div>
  );
}
