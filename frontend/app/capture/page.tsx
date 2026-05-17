"use client";

/**
 * Guided walkaround capture.
 *
 * Helps users record a complete, well-lit 360 walkaround instead of accepting
 * arbitrary clips that the pipeline can't rescue. We can't measure device
 * orientation reliably across browsers, so the flow is stage-driven: 8
 * canonical positions around the vehicle, each acknowledged manually before
 * advancing. While recording we sample the live video frame every 500ms to
 * compute brightness + a cheap blur proxy and warn the user in real time.
 *
 * On stop we hand the resulting Blob to the existing upload flow via
 * localStorage (so /inspect can pick it up) — keeping this page self-contained
 * means we don't have to touch the rest of the upload chain.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, Camera, Check, CheckCircle2, Loader2, Pause, Play, RotateCcw, Square, Sun } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";
import { runPreflight, uploadVideo } from "@/lib/api";

const STAGES = [
  { key: "front", label: "Front", hint: "Stand square to the front of the vehicle." },
  { key: "front_right", label: "Front-right corner", hint: "Move clockwise to the front-right quarter." },
  { key: "right", label: "Right side", hint: "Straight side-on, capturing both doors." },
  { key: "rear_right", label: "Rear-right corner", hint: "Continue clockwise to the rear-right corner." },
  { key: "rear", label: "Rear", hint: "Square to the back. Capture taillights + bumper." },
  { key: "rear_left", label: "Rear-left corner", hint: "Continue around." },
  { key: "left", label: "Left side", hint: "Both doors visible." },
  { key: "front_left", label: "Front-left corner", hint: "Close the loop." },
] as const;

const MIN_STAGE_SECONDS = 2.5;

interface LiveMetrics {
  brightness: number;
  blur: number;
}

function measureBrightnessAndBlur(video: HTMLVideoElement, canvas: HTMLCanvasElement): LiveMetrics | null {
  const w = 160;
  const h = 90;
  if (!video.videoWidth || !video.videoHeight) return null;
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) return null;
  ctx.drawImage(video, 0, 0, w, h);
  const data = ctx.getImageData(0, 0, w, h).data;

  // Convert to luma + accumulate stats. For the blur proxy we use the variance
  // of a 3x3 difference operator on the luma channel; high variance = high
  // edge content = sharper. Cheap and runs at ~60fps on mid mobile.
  const luma = new Float32Array(w * h);
  let sum = 0;
  for (let i = 0, j = 0; i < data.length; i += 4, j += 1) {
    const y = data[i] * 0.299 + data[i + 1] * 0.587 + data[i + 2] * 0.114;
    luma[j] = y;
    sum += y;
  }
  const brightness = sum / luma.length;

  let varSum = 0;
  let count = 0;
  for (let y = 1; y < h - 1; y++) {
    for (let x = 1; x < w - 1; x++) {
      const idx = y * w + x;
      const dx = luma[idx + 1] - luma[idx - 1];
      const dy = luma[idx + w] - luma[idx - w];
      varSum += dx * dx + dy * dy;
      count += 1;
    }
  }
  const blur = count > 0 ? varSum / count : 0;

  return { brightness, blur };
}

export default function CapturePage() {
  const router = useRouter();
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const analyzerCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const sampleTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const stageTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const [cameraReady, setCameraReady] = useState(false);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [recording, setRecording] = useState(false);
  const [stageIndex, setStageIndex] = useState(0);
  const [stageElapsed, setStageElapsed] = useState(0);
  const [totalElapsed, setTotalElapsed] = useState(0);
  const [metrics, setMetrics] = useState<LiveMetrics | null>(null);
  const [resultBlob, setResultBlob] = useState<Blob | null>(null);
  const [resultUrl, setResultUrl] = useState<string | null>(null);
  const [busyMessage, setBusyMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const stage = STAGES[stageIndex];
  const progress = ((stageIndex + Math.min(stageElapsed / MIN_STAGE_SECONDS, 1)) / STAGES.length) * 100;

  const startCamera = useCallback(async () => {
    setCameraError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: "environment" }, width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: false,
      });
      mediaStreamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play().catch(() => undefined);
      }
      setCameraReady(true);
    } catch (err) {
      const message =
        (err as Error)?.message || "Unable to access the camera. Check site permissions in your browser.";
      setCameraError(message);
    }
  }, []);

  useEffect(() => {
    startCamera();
    return () => {
      mediaStreamRef.current?.getTracks().forEach((t) => t.stop());
      if (sampleTimerRef.current) clearInterval(sampleTimerRef.current);
      if (stageTimerRef.current) clearInterval(stageTimerRef.current);
      if (resultUrl) URL.revokeObjectURL(resultUrl);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const startSampling = useCallback(() => {
    if (sampleTimerRef.current) return;
    sampleTimerRef.current = setInterval(() => {
      if (!videoRef.current || !analyzerCanvasRef.current) return;
      const m = measureBrightnessAndBlur(videoRef.current, analyzerCanvasRef.current);
      if (m) setMetrics(m);
    }, 500);
  }, []);

  const stopSampling = useCallback(() => {
    if (sampleTimerRef.current) {
      clearInterval(sampleTimerRef.current);
      sampleTimerRef.current = null;
    }
  }, []);

  const startStageTimer = useCallback(() => {
    if (stageTimerRef.current) clearInterval(stageTimerRef.current);
    stageTimerRef.current = setInterval(() => {
      setStageElapsed((e) => e + 0.5);
      setTotalElapsed((t) => t + 0.5);
    }, 500);
  }, []);

  const stopStageTimer = useCallback(() => {
    if (stageTimerRef.current) {
      clearInterval(stageTimerRef.current);
      stageTimerRef.current = null;
    }
  }, []);

  const beginRecording = useCallback(() => {
    if (!mediaStreamRef.current) return;
    setError(null);
    chunksRef.current = [];
    let mimeType = "video/mp4";
    if (typeof MediaRecorder !== "undefined" && !MediaRecorder.isTypeSupported("video/mp4")) {
      mimeType = MediaRecorder.isTypeSupported("video/webm;codecs=vp9") ? "video/webm;codecs=vp9" : "video/webm";
    }
    let recorder: MediaRecorder;
    try {
      recorder = new MediaRecorder(mediaStreamRef.current, { mimeType, videoBitsPerSecond: 4_500_000 });
    } catch (err) {
      setError(`Recorder unavailable: ${(err as Error).message}`);
      return;
    }
    mediaRecorderRef.current = recorder;
    recorder.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) chunksRef.current.push(e.data);
    };
    recorder.onstop = () => {
      const blob = new Blob(chunksRef.current, { type: recorder.mimeType || "video/mp4" });
      setResultBlob(blob);
      const url = URL.createObjectURL(blob);
      setResultUrl(url);
    };
    recorder.start(1000);
    setRecording(true);
    setStageIndex(0);
    setStageElapsed(0);
    setTotalElapsed(0);
    setResultBlob(null);
    setResultUrl(null);
    startSampling();
    startStageTimer();
  }, [startSampling, startStageTimer]);

  const advanceStage = useCallback(() => {
    if (stageElapsed < MIN_STAGE_SECONDS) return;
    setStageIndex((i) => {
      if (i >= STAGES.length - 1) return i;
      return i + 1;
    });
    setStageElapsed(0);
  }, [stageElapsed]);

  const stopRecording = useCallback(() => {
    stopSampling();
    stopStageTimer();
    setRecording(false);
    mediaRecorderRef.current?.stop();
  }, [stopSampling, stopStageTimer]);

  const resetCapture = useCallback(() => {
    stopSampling();
    stopStageTimer();
    if (resultUrl) URL.revokeObjectURL(resultUrl);
    setRecording(false);
    setStageIndex(0);
    setStageElapsed(0);
    setTotalElapsed(0);
    setResultBlob(null);
    setResultUrl(null);
    setError(null);
  }, [resultUrl, stopSampling, stopStageTimer]);

  const submitCapture = useCallback(async () => {
    if (!resultBlob) return;
    setBusyMessage("Running pre-flight check…");
    try {
      const ext = resultBlob.type.includes("mp4") ? "mp4" : "webm";
      const file = new File([resultBlob], `walkaround-${Date.now()}.${ext}`, { type: resultBlob.type });
      const preflight = await runPreflight(file);
      if (!preflight.can_proceed) {
        setBusyMessage(null);
        setError(
          `Pre-flight rejected the clip: ${preflight.issues.join(" · ")}. Re-record and try again.`,
        );
        return;
      }
      setBusyMessage("Uploading…");
      const result = await uploadVideo(file);
      router.push(`/job/${result.jobId}`);
    } catch (err) {
      setError((err as Error)?.message || "Upload failed");
      setBusyMessage(null);
    }
  }, [resultBlob, router]);

  const brightnessWarning =
    metrics && (metrics.brightness < 40 ? "Too dark — find better light." : metrics.brightness > 220 ? "Overexposed — reduce glare." : null);
  const blurWarning = metrics && metrics.blur < 20 ? "Blurry — slow down and hold steady." : null;
  const canAdvance = recording && stageElapsed >= MIN_STAGE_SECONDS && stageIndex < STAGES.length - 1;
  const canStop = recording && stageElapsed >= MIN_STAGE_SECONDS && stageIndex === STAGES.length - 1;

  return (
    <AppShell>
      <div className="mx-auto max-w-5xl p-4 sm:p-6 lg:p-8">
        <PageHeader
          eyebrow="Capture"
          title="Guided walkaround"
          description="Record a complete 360 in 8 stages with live quality feedback."
        />

        <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
          <Card className="overflow-hidden">
            <div className="relative aspect-video bg-black">
              <video
                ref={videoRef}
                playsInline
                muted
                autoPlay
                className="h-full w-full object-cover"
              />
              <canvas ref={analyzerCanvasRef} className="hidden" />
              {!cameraReady && !cameraError && (
                <div className="absolute inset-0 flex items-center justify-center text-white">
                  <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                  Requesting camera…
                </div>
              )}
              {cameraError && (
                <div className="absolute inset-0 flex flex-col items-center justify-center bg-black/70 p-4 text-center text-white">
                  <AlertTriangle className="mb-2 h-6 w-6 text-amber-400" />
                  <p className="text-sm">{cameraError}</p>
                  <Button variant="outline" size="sm" className="mt-3" onClick={startCamera}>
                    Try again
                  </Button>
                </div>
              )}

              {/* Live overlays */}
              {recording && (
                <>
                  <div className="absolute left-3 top-3 flex items-center gap-2 rounded-md bg-black/60 px-2 py-1 text-xs text-white">
                    <span className="h-2 w-2 animate-pulse rounded-full bg-red-500" />
                    REC · {totalElapsed.toFixed(1)}s
                  </div>
                  <div className="absolute right-3 top-3 rounded-md bg-black/60 px-2 py-1 text-xs text-white">
                    Stage {stageIndex + 1}/{STAGES.length}
                  </div>
                  <div className="absolute inset-x-3 bottom-3 rounded-md bg-black/70 p-3 text-white">
                    <div className="text-xs uppercase tracking-wide text-white/60">
                      Now capturing
                    </div>
                    <div className="text-base font-semibold">{stage.label}</div>
                    <div className="mt-0.5 text-xs text-white/80">{stage.hint}</div>
                    {(brightnessWarning || blurWarning) && (
                      <div className="mt-2 flex flex-wrap gap-2">
                        {brightnessWarning && (
                          <span className="flex items-center gap-1 rounded bg-amber-500/20 px-2 py-0.5 text-xs text-amber-200">
                            <Sun className="h-3 w-3" /> {brightnessWarning}
                          </span>
                        )}
                        {blurWarning && (
                          <span className="flex items-center gap-1 rounded bg-amber-500/20 px-2 py-0.5 text-xs text-amber-200">
                            <AlertTriangle className="h-3 w-3" /> {blurWarning}
                          </span>
                        )}
                      </div>
                    )}
                  </div>
                </>
              )}
            </div>

            <CardContent className="space-y-4 p-4">
              <Progress value={progress} className="h-2" />
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="text-sm text-muted-foreground">
                  {recording
                    ? `Hold each stage for at least ${MIN_STAGE_SECONDS}s. Currently ${stageElapsed.toFixed(1)}s on ${stage.label}.`
                    : resultBlob
                    ? "Recording complete. Review and submit, or re-record."
                    : "Hit Start, then move clockwise around the vehicle."}
                </div>
                <div className="flex flex-wrap gap-2">
                  {!recording && !resultBlob && (
                    <Button onClick={beginRecording} disabled={!cameraReady} className="gap-2">
                      <Play className="h-4 w-4" /> Start
                    </Button>
                  )}
                  {recording && (
                    <>
                      <Button
                        variant="outline"
                        onClick={advanceStage}
                        disabled={!canAdvance}
                        className="gap-2"
                      >
                        <Check className="h-4 w-4" /> Next stage
                      </Button>
                      <Button onClick={stopRecording} disabled={!canStop} variant="destructive" className="gap-2">
                        <Square className="h-4 w-4" /> Finish
                      </Button>
                    </>
                  )}
                  {!recording && resultBlob && (
                    <>
                      <Button variant="outline" onClick={resetCapture} className="gap-2">
                        <RotateCcw className="h-4 w-4" /> Re-record
                      </Button>
                      <Button onClick={submitCapture} disabled={Boolean(busyMessage)} className="gap-2">
                        {busyMessage ? <Loader2 className="h-4 w-4 animate-spin" /> : <Camera className="h-4 w-4" />}
                        {busyMessage || "Submit for inspection"}
                      </Button>
                    </>
                  )}
                </div>
              </div>

              {resultUrl && !recording && (
                <video
                  src={resultUrl}
                  controls
                  className="mt-2 w-full rounded-md border bg-black"
                />
              )}

              {error && (
                <div className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
                  {error}
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Stages</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {STAGES.map((s, i) => {
                const done = recording ? i < stageIndex : !recording && resultBlob && i <= STAGES.length - 1;
                const current = recording && i === stageIndex;
                return (
                  <div
                    key={s.key}
                    className={cn(
                      "flex items-start gap-3 rounded-md border px-3 py-2 text-sm",
                      current && "border-primary bg-primary/5",
                      done && !current && "border-emerald-500/30 bg-emerald-500/5",
                    )}
                  >
                    <div className="mt-0.5">
                      {done && !current ? (
                        <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                      ) : current ? (
                        <Loader2 className="h-4 w-4 animate-spin text-primary" />
                      ) : (
                        <span className="block h-4 w-4 rounded-full border border-border" />
                      )}
                    </div>
                    <div>
                      <div className="font-medium">{s.label}</div>
                      <div className="text-xs text-muted-foreground">{s.hint}</div>
                    </div>
                  </div>
                );
              })}

              <div className="mt-4 rounded-md border bg-secondary/30 p-3 text-xs text-muted-foreground">
                <p className="font-medium text-foreground">Tips</p>
                <ul className="mt-1 list-inside list-disc space-y-1">
                  <li>Stand ~2 m from the vehicle.</li>
                  <li>Avoid direct sun or strong shadows.</li>
                  <li>Move slowly to keep frames sharp.</li>
                  <li>Capture wheels by tilting down briefly per side.</li>
                </ul>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </AppShell>
  );
}
