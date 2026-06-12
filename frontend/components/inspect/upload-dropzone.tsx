"use client"

import React from "react"

import { useState, useCallback, useEffect, useRef } from "react"
import { Upload, Film, X, FileVideo, CheckCircle2, AlertCircle, ShieldCheck, AlertTriangle } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Callout } from "@/components/ui/callout"
import { Progress } from "@/components/ui/progress"
import { cn } from "@/lib/utils"
import { uploadVideo, runPreflight, type PreflightResult } from "@/lib/api"
import { getApiErrorMessage } from "@/lib/api-error"
import {
  EMPTY_IDENTITY,
  IdentityFields,
  identityPayload,
  type IdentityMetadata,
} from "@/components/inspect/identity-fields"

export interface UploadedFile {
  id: string
  name: string
  size: number
  progress: number
  status: "preflight" | "preflight_blocked" | "uploading" | "processing" | "complete" | "error"
  jobId?: string
  error?: string
  preflight?: PreflightResult
  rawFile?: File
  rawOdometerImage?: File | null
}

interface UploadDropzoneProps {
  onFilesUploaded: (files: UploadedFile[]) => void
}

export function UploadDropzone({ onFilesUploaded }: UploadDropzoneProps) {
  const [isDragging, setIsDragging] = useState(false)
  const [files, setFiles] = useState<UploadedFile[]>([])
  const [identityMetadata, setIdentityMetadata] = useState<IdentityMetadata>(EMPTY_IDENTITY)
  // The upload may start long after the video is dropped (pre-flight) and
  // the user may still be typing identity fields. Read them through a ref at
  // upload time so late edits aren't silently dropped.
  const identityRef = useRef<IdentityMetadata>(EMPTY_IDENTITY)
  const fileInputRef = useRef<HTMLInputElement | null>(null)

  // Keep the parent in sync with the FULL file list on every change so a
  // second uploaded video never silently replaces the first one.
  useEffect(() => {
    onFilesUploaded(files)
  }, [files, onFilesUploaded])

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(true)
  }, [])

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
  }, [])

  const handleUpload = useCallback(async (file: File, odometerImage?: File | null, opts?: { skipPreflight?: boolean }) => {
    const newFile: UploadedFile = {
      id: Math.random().toString(36).substring(7),
      name: file.name,
      size: file.size,
      progress: 0,
      status: opts?.skipPreflight ? "uploading" : "preflight",
      rawFile: file,
      rawOdometerImage: odometerImage,
    }

    setFiles((prev) => [...prev, newFile])

    // Pre-flight quality gate. Surface issues before the user waits for the
    // full pipeline. Fails open if the ML service is down.
    if (!opts?.skipPreflight) {
      try {
        const preflight = await runPreflight(file)
        setFiles((prev) =>
          prev.map((f) =>
            f.id === newFile.id ? { ...f, preflight } : f,
          ),
        )
        if (!preflight.can_proceed) {
          setFiles((prev) =>
            prev.map((f) =>
              f.id === newFile.id ? { ...f, status: "preflight_blocked" } : f,
            ),
          )
          return
        }
      } catch (preflightError) {
        // Fail open — the backend route also fails open, but defend in depth.
        console.warn("Pre-flight check failed; continuing to upload", preflightError)
      }
      setFiles((prev) =>
        prev.map((f) =>
          f.id === newFile.id ? { ...f, status: "uploading" } : f,
        ),
      )
    }

    try {
      const result = await uploadVideo(
        file,
        odometerImage,
        (progress) => {
          setFiles((prev) =>
            prev.map((f) => (f.id === newFile.id ? { ...f, progress } : f))
          )
        },
        identityPayload(identityRef.current),
      )

      // Upload complete, now processing
      setFiles((prev) =>
        prev.map((f) =>
          f.id === newFile.id
            ? { ...f, progress: 100, status: "processing", jobId: result.jobId }
            : f
        )
      )

      // Mark as complete after a short delay
      setTimeout(() => {
        setFiles((prev) =>
          prev.map((f) =>
            f.id === newFile.id ? { ...f, status: "complete" } : f
          )
        )
      }, 500)
    } catch (error) {
      setFiles((prev) =>
        prev.map((f) =>
          f.id === newFile.id
            ? {
                ...f,
                status: "error",
                error: getApiErrorMessage(error, "Upload failed"),
              }
            : f
        )
      )
    }
  }, [])

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setIsDragging(false)

      const droppedFiles = Array.from(e.dataTransfer.files)
      const videoFiles = droppedFiles.filter((f) => f.type.startsWith("video/"))
      const imageFiles = droppedFiles.filter((f) => f.type.startsWith("image/"))

      videoFiles.forEach((file) => {
        handleUpload(file, imageFiles[0] || null)
      })
    },
    [handleUpload]
  )

  const handleFileInput = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      if (e.target.files) {
        const selectedFiles = Array.from(e.target.files)
        const videoFiles = selectedFiles.filter((f) => f.type.startsWith("video/"))
        const imageFiles = selectedFiles.filter((f) => f.type.startsWith("image/"))

        videoFiles.forEach((file) => {
          handleUpload(file, imageFiles[0] || null)
        })
      }
    },
    [handleUpload]
  )

  const removeFile = (id: string) => {
    setFiles((prev) => prev.filter((f) => f.id !== id))
  }

  const uploadAnyway = useCallback(
    (file: UploadedFile) => {
      if (!file.rawFile) return
      const rawFile = file.rawFile
      const rawOdo = file.rawOdometerImage
      setFiles((prev) => prev.filter((f) => f.id !== file.id))
      handleUpload(rawFile, rawOdo, { skipPreflight: true })
    },
    [handleUpload],
  )

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024 * 1024) {
      return `${(bytes / 1024).toFixed(1)} KB`
    }
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  const updateIdentityMetadata = (field: keyof IdentityMetadata, value: string) => {
    identityRef.current = { ...identityRef.current, [field]: value }
    setIdentityMetadata((prev) => ({ ...prev, [field]: value }))
  }

  const openFilePicker = () => fileInputRef.current?.click()

  return (
    <div className="space-y-4">
      <div
        role="button"
        tabIndex={0}
        aria-label="Upload a 360° vehicle video"
        onClick={openFilePicker}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault()
            openFilePicker()
          }
        }}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={cn(
          "relative flex min-h-[320px] cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          isDragging
            ? "border-primary bg-primary/5"
            : "border-border bg-secondary/30 hover:border-primary/50 hover:bg-secondary/50"
        )}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept="video/*,image/*"
          multiple
          onChange={handleFileInput}
          className="sr-only"
          tabIndex={-1}
          aria-hidden="true"
        />

        <div className="flex flex-col items-center gap-4 p-8 text-center">
          <div className="flex h-16 w-16 items-center justify-center rounded-lg bg-primary/10">
            <Upload className="h-8 w-8 text-primary" />
          </div>

          <div>
            <p className="text-lg font-semibold">
              Drop your 360° vehicle video here
            </p>
            <p className="mt-1 text-sm text-muted-foreground">
              or click to browse from your computer
            </p>
          </div>

          <div className="flex items-center gap-4 text-xs text-muted-foreground">
            <span className="flex items-center gap-1">
              <Film className="h-3 w-3" />
              MP4, MOV, AVI
            </span>
            <span>Max 2GB</span>
            <span>Odometer image optional</span>
          </div>

          <Button
            variant="outline"
            className="mt-2 bg-transparent"
            onClick={(e) => {
              e.stopPropagation()
              openFilePicker()
            }}
          >
            Browse Files
          </Button>
        </div>
      </div>

      <IdentityFields value={identityMetadata} onFieldChange={updateIdentityMetadata} />

      {files.length > 0 && (
        <div className="space-y-3">
          <h3 className="text-sm font-medium">Uploaded Files</h3>
          {files.map((file) => (
            <div
              key={file.id}
              className="flex items-center gap-4 rounded-lg border border-border bg-card p-4"
            >
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-secondary">
                <FileVideo className="h-5 w-5 text-primary" />
              </div>

              <div className="flex-1">
                <div className="flex items-center justify-between">
                  <p className="font-medium">{file.name}</p>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-6 w-6"
                    aria-label={`Remove ${file.name}`}
                    onClick={() => removeFile(file.id)}
                  >
                    <X className="h-4 w-4" />
                  </Button>
                </div>
                <div className="mt-1 flex items-center gap-2">
                  <span className="text-xs text-muted-foreground">
                    {formatFileSize(file.size)}
                  </span>
                  {file.status === "preflight" && (
                    <>
                      <span className="text-xs text-muted-foreground">·</span>
                      <span className="flex items-center gap-1 text-xs text-primary">
                        <ShieldCheck className="h-3 w-3" />
                        Pre-flight check…
                      </span>
                    </>
                  )}
                  {file.status === "preflight_blocked" && (
                    <>
                      <span className="text-xs text-muted-foreground">·</span>
                      <span className="flex items-center gap-1 text-xs text-amber-600">
                        <AlertTriangle className="h-3 w-3" />
                        Pre-flight failed
                      </span>
                    </>
                  )}
                  {file.status === "uploading" && (
                    <>
                      <span className="text-xs text-muted-foreground">·</span>
                      <span className="text-xs text-primary">
                        Uploading {Math.round(file.progress)}%
                      </span>
                    </>
                  )}
                  {file.status === "processing" && (
                    <>
                      <span className="text-xs text-muted-foreground">·</span>
                      <span className="text-xs text-accent">
                        AI Processing...
                      </span>
                    </>
                  )}
                  {file.status === "complete" && (
                    <>
                      <span className="text-xs text-muted-foreground">·</span>
                      <span className="flex items-center gap-1 text-xs text-emerald-500">
                        <CheckCircle2 className="h-3 w-3" />
                        Complete
                      </span>
                    </>
                  )}
                  {file.status === "error" && (
                    <>
                      <span className="text-xs text-muted-foreground">·</span>
                      <span className="flex items-center gap-1 text-xs text-destructive">
                        <AlertCircle className="h-3 w-3" />
                        Error
                      </span>
                    </>
                  )}
                </div>
                {(file.status === "uploading" || file.status === "processing") && (
                  <Progress
                    value={file.status === "processing" ? 100 : file.progress}
                    className="mt-2 h-1"
                  />
                )}
                {file.status === "preflight_blocked" && file.preflight && (
                  <Callout variant="warning" icon={false} className="mt-2 p-2 text-xs">
                    <p className="font-medium">Fix these before re-uploading:</p>
                    <ul className="mt-1 list-inside list-disc space-y-0.5">
                      {file.preflight.issues.map((issue) => (
                        <li key={issue}>{issue}</li>
                      ))}
                    </ul>
                    <div className="mt-2 flex flex-wrap items-center gap-2">
                      <Button type="button" size="sm" variant="outline" onClick={() => uploadAnyway(file)}>
                        Upload anyway
                      </Button>
                      <span className="text-[10px] text-muted-foreground">
                        Coverage {Math.round((file.preflight.coverage_estimate ?? 0) * 100)}% ·
                        {" "}Vehicle visible {Math.round((file.preflight.vehicle_visible_ratio ?? 0) * 100)}%
                      </span>
                    </div>
                  </Callout>
                )}
                {file.preflight?.warnings?.length ? (
                  <div className="mt-2 rounded-md border border-border bg-secondary/40 p-2 text-xs text-muted-foreground">
                    {file.preflight.warnings.map((w) => (
                      <div key={w}>· {w}</div>
                    ))}
                  </div>
                ) : null}
                {file.status === "error" && file.error && (
                  <p className="mt-1 text-xs text-destructive">{file.error}</p>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

