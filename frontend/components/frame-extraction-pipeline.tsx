"use client"

import { useState, useEffect, useRef } from "react"
import Image from "next/image"
import { Play, Film, Grid3X3, Layers, Zap, CheckCircle, Clock, Pause } from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

export function FrameExtractionPipeline() {
  const [isPlaying, setIsPlaying] = useState(false)
  const [currentStep, setCurrentStep] = useState(0)
  const [extractedFrames, setExtractedFrames] = useState<number[]>([])
  const [capturedThumbnails, setCapturedThumbnails] = useState<string[]>([])
  const videoRef = useRef<HTMLVideoElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)

  const totalFrames = 12
  const pipelineSteps = [
    { id: 0, label: "Video Input", icon: Film, description: "360° walk-around video loaded" },
    { id: 1, label: "Frame Sampling", icon: Grid3X3, description: "Extracting frames at fixed intervals" },
    { id: 2, label: "Quality Filter", icon: Layers, description: "Removing blurry/duplicate frames" },
    { id: 3, label: "AI Processing", icon: Zap, description: "Running detection models" },
    { id: 4, label: "Complete", icon: CheckCircle, description: "All frames analyzed" },
  ]

  const captureFrame = () => {
    const video = videoRef.current
    const canvas = canvasRef.current
    if (!video || !canvas) return null

    const ctx = canvas.getContext("2d")
    if (!ctx) return null

    canvas.width = 160
    canvas.height = 90
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height)
    return canvas.toDataURL("image/jpeg", 0.8)
  }

  useEffect(() => {
    if (!isPlaying) return

    const video = videoRef.current
    if (video) {
      video.play()
    }

    const interval = setInterval(() => {
      setExtractedFrames((prev) => {
        if (prev.length >= totalFrames) {
          setIsPlaying(false)
          setCurrentStep(4)
          if (video) video.pause()
          return prev
        }

        // Capture actual frame from video
        const thumbnail = captureFrame()
        if (thumbnail) {
          setCapturedThumbnails((prevThumbs) => [...prevThumbs, thumbnail])
        }

        const newLength = prev.length + 1
        if (newLength <= 4) setCurrentStep(1)
        else if (newLength <= 8) setCurrentStep(2)
        else if (newLength <= 11) setCurrentStep(3)
        else setCurrentStep(4)
        return [...prev, newLength]
      })
    }, 600)

    return () => clearInterval(interval)
  }, [isPlaying])

  const resetDemo = () => {
    setIsPlaying(false)
    setCurrentStep(0)
    setExtractedFrames([])
    setCapturedThumbnails([])
    const video = videoRef.current
    if (video) {
      video.pause()
      video.currentTime = 0
    }
  }

  const startDemo = () => {
    resetDemo()
    setTimeout(() => setIsPlaying(true), 100)
  }

  const frameLabels = [
    "Front View",
    "Front Left",
    "Left Side",
    "Rear Left",
    "Rear View",
    "Rear Right",
    "Right Side",
    "Front Right",
    "Dashboard",
    "Odometer",
    "Exhaust",
    "Interior",
  ]

  return (
    <section id="pipeline" className="py-20 md:py-32 bg-secondary/30">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-2xl text-center">
          <p className="text-sm font-medium uppercase tracking-wider text-primary">Frame Extraction Pipeline</p>
          <h2 className="mt-4 text-3xl font-bold text-foreground sm:text-4xl text-balance">
            Watch the extraction process in action
          </h2>
          <p className="mt-4 text-muted-foreground text-pretty">
            See how VIP processes your video footage frame by frame, extracting key angles for comprehensive analysis.
          </p>
        </div>

        {/* Pipeline Status */}
        <div className="mt-12 flex flex-wrap justify-center gap-2 md:gap-4">
          {pipelineSteps.map((step) => (
            <div
              key={step.id}
              className={cn(
                "flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium transition-all",
                currentStep >= step.id
                  ? "bg-primary text-primary-foreground"
                  : "bg-card border border-border text-muted-foreground",
              )}
            >
              <step.icon className="h-4 w-4" />
              <span className="hidden sm:inline">{step.label}</span>
            </div>
          ))}
        </div>

        {/* Main Visualization */}
        <div className="mt-12 grid gap-8 lg:grid-cols-2">
          <div className="rounded-2xl border border-border bg-card p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-foreground">Source Video</h3>
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Clock className="h-4 w-4" />
                <span>Real 360° footage</span>
              </div>
            </div>

            {/* Real Video Player */}
            <div className="relative aspect-video rounded-xl overflow-hidden bg-black">
              <video
                ref={videoRef}
                className="h-full w-full object-cover"
                muted
                playsInline
                loop
                crossOrigin="anonymous"
                poster="/car-walk-around-video-thumbnail.jpg"
              >
                <source
                  src="https://videos.pexels.com/video-files/3764984/3764984-uhd_2560_1440_25fps.mp4"
                  type="video/mp4"
                />
                Your browser does not support the video tag.
              </video>

              {/* Hidden canvas for frame capture */}
              <canvas ref={canvasRef} className="hidden" />

              {/* Progress bar */}
              <div className="absolute bottom-0 left-0 right-0 h-1 bg-slate-700">
                <div
                  className="h-full bg-primary transition-all duration-300"
                  style={{ width: `${(extractedFrames.length / totalFrames) * 100}%` }}
                />
              </div>

              {/* Play/Pause overlay indicator */}
              {!isPlaying && extractedFrames.length === 0 && (
                <div className="absolute inset-0 flex items-center justify-center bg-black/40">
                  <div className="text-center">
                    <div className="mx-auto h-16 w-16 rounded-full bg-primary/20 flex items-center justify-center mb-2">
                      <Play className="h-8 w-8 text-primary" />
                    </div>
                    <p className="text-sm text-white/80">Click Start to begin extraction</p>
                  </div>
                </div>
              )}

              {/* Scanning overlay */}
              {isPlaying && (
                <div className="absolute inset-0 pointer-events-none">
                  <div
                    className="absolute top-0 bottom-0 w-1 bg-primary/80"
                    style={{
                      left: `${(extractedFrames.length / totalFrames) * 100}%`,
                      boxShadow: "0 0 30px rgba(14, 165, 233, 0.8)",
                    }}
                  />
                  <div className="absolute top-4 right-4 flex items-center gap-2 rounded-full bg-destructive px-3 py-1">
                    <span className="relative flex h-2 w-2">
                      <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-white opacity-75" />
                      <span className="relative inline-flex h-2 w-2 rounded-full bg-white" />
                    </span>
                    <span className="text-xs font-medium text-white">EXTRACTING</span>
                  </div>
                </div>
              )}
            </div>

            {/* Controls */}
            <div className="mt-4 flex items-center justify-center gap-4">
              <Button onClick={startDemo} disabled={isPlaying} className="gap-2">
                {isPlaying ? (
                  <>
                    <Pause className="h-4 w-4" />
                    Extracting...
                  </>
                ) : (
                  <>
                    <Play className="h-4 w-4" />
                    Start Extraction
                  </>
                )}
              </Button>
              <Button variant="outline" onClick={resetDemo} disabled={isPlaying}>
                Reset
              </Button>
            </div>
          </div>

          {/* Extracted Frames Grid */}
          <div className="rounded-2xl border border-border bg-card p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-foreground">Extracted Frames</h3>
              <div className="flex items-center gap-2 text-sm">
                <span className="font-mono text-primary">{extractedFrames.length}</span>
                <span className="text-muted-foreground">/ {totalFrames} frames</span>
              </div>
            </div>

            <div className="grid grid-cols-4 gap-2">
              {Array.from({ length: totalFrames }).map((_, index) => {
                const isExtracted = extractedFrames.includes(index + 1)
                const isCurrentlyExtracting = isPlaying && extractedFrames.length === index
                const thumbnail = capturedThumbnails[index]

                return (
                  <div
                    key={index}
                    className={cn(
                      "aspect-square rounded-lg border-2 transition-all duration-300 overflow-hidden relative",
                      isExtracted
                        ? "border-primary bg-primary/10"
                        : isCurrentlyExtracting
                          ? "border-primary/50 bg-primary/5 animate-pulse"
                          : "border-border bg-secondary/50",
                    )}
                  >
                    {isExtracted && thumbnail ? (
                      <>
                        <Image
                          src={thumbnail || "/placeholder.svg"}
                          alt={frameLabels[index]}
                          fill
                          className="object-cover"
                          unoptimized
                        />
                        <div className="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent" />
                        <div className="absolute bottom-0 left-0 right-0 p-1">
                          <span className="text-[9px] text-white font-medium leading-tight block truncate">
                            {frameLabels[index]}
                          </span>
                        </div>
                        <CheckCircle className="absolute top-1 right-1 h-3 w-3 text-primary" />
                      </>
                    ) : (
                      <div className="h-full w-full flex flex-col items-center justify-center p-1">
                        <span className="text-xs text-muted-foreground/50">F{String(index + 1).padStart(2, "0")}</span>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>

            {/* Frame Metadata */}
            {extractedFrames.length > 0 && (
              <div className="mt-4 rounded-lg bg-secondary/50 p-4">
                <p className="text-xs font-mono text-muted-foreground">
                  <span className="text-primary">Latest:</span> Frame {extractedFrames[extractedFrames.length - 1]} -{" "}
                  {frameLabels[extractedFrames.length - 1]}
                </p>
                <p className="text-xs font-mono text-muted-foreground mt-1">
                  <span className="text-primary">Status:</span>{" "}
                  {extractedFrames.length === totalFrames ? "All frames captured" : "Capturing frames..."}
                </p>
              </div>
            )}
          </div>
        </div>

        {/* Technical Details */}
        <div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[
            { label: "Frame Rate", value: "25 fps", detail: "Video input" },
            { label: "Extraction Interval", value: "Every 75 frames", detail: "~3 seconds" },
            { label: "Quality Threshold", value: "> 85%", detail: "Blur detection" },
            { label: "Output Format", value: "JPEG", detail: "Optimized for AI" },
          ].map((stat, index) => (
            <div key={index} className="rounded-xl border border-border bg-card p-4 text-center">
              <p className="text-2xl font-bold text-primary">{stat.value}</p>
              <p className="text-sm font-medium text-foreground">{stat.label}</p>
              <p className="text-xs text-muted-foreground">{stat.detail}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
