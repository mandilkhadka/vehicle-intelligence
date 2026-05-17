"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { CheckCircle2, Circle, Loader2, XCircle } from "lucide-react";
import { getJobStatus } from "@/lib/api";
import { PROGRESS } from "@/lib/constants";
import { showError } from "@/lib/toast";
import { cn } from "@/lib/utils";

// Exponential backoff for polling. Successful polls reset to BASE_INTERVAL_MS;
// each consecutive fetch failure doubles the wait up to MAX_INTERVAL_MS so a
// flaky network or slow ML service doesn't burn ~30 reqs/min for no reason.
const BASE_INTERVAL_MS = 2000;
const MAX_INTERVAL_MS = 30000;

const T = PROGRESS.THRESHOLDS;

const STAGES: Array<{ label: string; at: number }> = [
  { label: "Video uploaded", at: T.UPLOAD_COMPLETE },
  { label: "Extracting frames", at: T.FRAME_EXTRACTION },
  { label: "Identifying vehicle", at: T.VEHICLE_IDENTIFIED },
  { label: "Reading odometer", at: T.ODOMETER_READ },
  { label: "Detecting damage", at: T.DAMAGE_DETECTED },
  { label: "Generating report", at: T.REPORT_GENERATED },
];

interface JobStatusProps {
  jobId: string;
}

export default function JobStatus({ jobId }: JobStatusProps) {
  const [status, setStatus] = useState<string>("pending");
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();
  const stoppedRef = useRef(false);
  const fetchErrorShownRef = useRef(false);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const consecutiveFailuresRef = useRef(0);
  const runPollRef = useRef<() => void>(() => {});
  const [retryNonce, setRetryNonce] = useState(0);

  const scheduleNext = useCallback((delay: number) => {
    if (stoppedRef.current) return;
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    timeoutRef.current = setTimeout(() => runPollRef.current(), delay);
  }, []);

  const runPoll = useCallback(async () => {
    if (stoppedRef.current) return;
    try {
      const data = await getJobStatus(jobId);
      fetchErrorShownRef.current = false;
      consecutiveFailuresRef.current = 0;
      setError(null);
      setStatus(data.status);
      setProgress(data.progress ?? 0);

      if (data.status === "completed") {
        stoppedRef.current = true;
        const inspectionId = data.inspectionId || data.inspection_id;
        if (inspectionId) {
          setTimeout(() => router.push(`/inspection/${inspectionId}`), 800);
        }
        return;
      }
      if (data.status === "failed") {
        stoppedRef.current = true;
        setError(data.error_message || data.error || "Processing failed");
        return;
      }
      scheduleNext(BASE_INTERVAL_MS);
    } catch (err) {
      consecutiveFailuresRef.current += 1;
      const delay = Math.min(
        BASE_INTERVAL_MS * Math.pow(2, consecutiveFailuresRef.current),
        MAX_INTERVAL_MS,
      );
      setError(`Unable to refresh job status. Retrying in ${Math.round(delay / 1000)}s…`);
      if (!fetchErrorShownRef.current) {
        showError("Failed to fetch job status", err);
        fetchErrorShownRef.current = true;
      }
      scheduleNext(delay);
    }
  }, [jobId, router, scheduleNext]);

  useEffect(() => {
    runPollRef.current = runPoll;
  }, [runPoll]);

  useEffect(() => {
    stoppedRef.current = false;
    fetchErrorShownRef.current = false;
    consecutiveFailuresRef.current = 0;
    runPoll();
    return () => {
      stoppedRef.current = true;
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, [jobId, runPoll, retryNonce]);

  const handleManualRetry = () => {
    if (stoppedRef.current && status !== "failed") return;
    stoppedRef.current = false;
    consecutiveFailuresRef.current = 0;
    setError(null);
    setRetryNonce((n) => n + 1);
  };

  const isFailed = status === "failed";
  const isDone = status === "completed";

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="capitalize">{status}</CardTitle>
        <span className="text-sm font-medium text-muted-foreground">{progress}%</span>
      </CardHeader>
      <CardContent className="space-y-6">
        <Progress
          value={progress}
          className={cn(
            "h-2",
            isFailed && "[&>div]:bg-destructive",
            isDone && "[&>div]:bg-emerald-500",
          )}
        />

        <ul className="space-y-2">
          {STAGES.map((stage) => {
            const reached = progress >= stage.at;
            const active = !reached && progress >= (STAGES[STAGES.indexOf(stage) - 1]?.at ?? 0);
            return (
              <li key={stage.label} className="flex items-center gap-3 text-sm">
                {reached ? (
                  <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                ) : active && !isFailed ? (
                  <Loader2 className="h-4 w-4 animate-spin text-primary" />
                ) : (
                  <Circle className="h-4 w-4 text-muted-foreground/40" />
                )}
                <span className={cn(reached ? "text-foreground" : "text-muted-foreground")}>
                  {stage.label}
                </span>
              </li>
            );
          })}
        </ul>

        {progress >= T.UPLOAD_COMPLETE && progress < T.FRAME_EXTRACTION && !isFailed && (
          <p className="text-xs text-muted-foreground">
            Initializing AI models — this may take 30–60s on the first run.
          </p>
        )}

        {error && !isFailed && !isDone && (
          <div className="flex items-center justify-between gap-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-700 dark:border-amber-900/40 dark:bg-amber-950/30 dark:text-amber-300">
            <span>{error}</span>
            <Button type="button" size="sm" variant="outline" onClick={handleManualRetry}>
              Retry now
            </Button>
          </div>
        )}

        {isDone && (
          <p className="flex items-center gap-2 text-sm font-medium text-emerald-600">
            <CheckCircle2 className="h-4 w-4" /> Complete — redirecting to results…
          </p>
        )}

        {isFailed && (
          <div className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
            <XCircle className="mt-0.5 h-4 w-4 shrink-0" />
            <span>{error || "An unexpected error occurred."}</span>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
