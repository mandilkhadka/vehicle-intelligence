"use client"

import React from "react"

import { useState, useCallback } from "react"
import { Upload, Film, X, FileVideo, CheckCircle2, AlertCircle, ShieldCheck, AlertTriangle } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Progress } from "@/components/ui/progress"
import { cn } from "@/lib/utils"
import { uploadVideo, runPreflight, type PreflightResult } from "@/lib/api"

interface UploadedFile {
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

interface IdentityMetadata {
  vehicle_brand: string
  vehicle_model: string
  vin: string
  registration: string
  vehicle_year: string
  vehicle_variant: string
  vehicle_type: string
  vehicle_category: string
}

export function UploadDropzone({ onFilesUploaded }: UploadDropzoneProps) {
  const [isDragging, setIsDragging] = useState(false)
  const [files, setFiles] = useState<UploadedFile[]>([])
  const [identityMetadata, setIdentityMetadata] = useState<IdentityMetadata>({
    vehicle_brand: "",
    vehicle_model: "",
    vin: "",
    registration: "",
    vehicle_year: "",
    vehicle_variant: "",
    vehicle_type: "",
    vehicle_category: "",
  })

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
        identityPayload(identityMetadata),
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
        onFilesUploaded([{ ...newFile, progress: 100, status: "complete", jobId: result.jobId }])
      }, 500)
    } catch (error: any) {
      setFiles((prev) =>
        prev.map((f) =>
          f.id === newFile.id
            ? {
                ...f,
                status: "error",
                error: error?.response?.data?.error || error?.message || "Upload failed",
              }
            : f
        )
      )
    }
  }, [identityMetadata, onFilesUploaded])

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
    setFiles((prev) => {
      const next = prev.filter((f) => f.id !== id)
      onFilesUploaded(next)
      return next
    })
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
    setIdentityMetadata((prev) => ({ ...prev, [field]: value }))
  }

  return (
    <div className="space-y-4">
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={cn(
          "relative flex min-h-[320px] cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed transition-all",
          isDragging
            ? "border-primary bg-primary/5"
            : "border-border bg-secondary/30 hover:border-primary/50 hover:bg-secondary/50"
        )}
      >
        <input
          type="file"
          accept="video/*,image/*"
          multiple
          onChange={handleFileInput}
          className="absolute inset-0 cursor-pointer opacity-0"
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

          <Button variant="outline" className="mt-2 bg-transparent">
            Browse Files
          </Button>
        </div>
      </div>

      <div className="rounded-lg border border-border bg-card p-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field
            id="vehicle_brand"
            label="Make"
            value={identityMetadata.vehicle_brand}
            onChange={(value) => updateIdentityMetadata("vehicle_brand", value)}
          />
          <Field
            id="vehicle_model"
            label="Model"
            value={identityMetadata.vehicle_model}
            onChange={(value) => updateIdentityMetadata("vehicle_model", value)}
          />
          <Field
            id="vin"
            label="VIN / chassis"
            value={identityMetadata.vin}
            onChange={(value) => updateIdentityMetadata("vin", value)}
          />
          <Field
            id="registration"
            label="Registration"
            value={identityMetadata.registration}
            onChange={(value) => updateIdentityMetadata("registration", value)}
          />
          <Field
            id="vehicle_year"
            label="Year"
            value={identityMetadata.vehicle_year}
            onChange={(value) => updateIdentityMetadata("vehicle_year", value)}
          />
          <Field
            id="vehicle_variant"
            label="Trim / variant"
            value={identityMetadata.vehicle_variant}
            onChange={(value) => updateIdentityMetadata("vehicle_variant", value)}
          />
          <Field
            id="vehicle_type"
            label="Vehicle type"
            value={identityMetadata.vehicle_type}
            onChange={(value) => updateIdentityMetadata("vehicle_type", value)}
          />
          <Field
            id="vehicle_category"
            label="Category"
            value={identityMetadata.vehicle_category}
            onChange={(value) => updateIdentityMetadata("vehicle_category", value)}
          />
        </div>
      </div>

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
                  <div className="mt-2 rounded-md border border-amber-300 bg-amber-50 p-2 text-xs text-amber-900 dark:border-amber-900/40 dark:bg-amber-950/30 dark:text-amber-200">
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
                  </div>
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

function identityPayload(metadata: IdentityMetadata) {
  const payload = {
    vehicle_identity_source: "upload_form",
    vehicle_brand: metadata.vehicle_brand.trim(),
    vehicle_model: metadata.vehicle_model.trim(),
    vin: metadata.vin.trim(),
    registration: metadata.registration.trim(),
    vehicle_year: metadata.vehicle_year.trim(),
    vehicle_variant: metadata.vehicle_variant.trim(),
    vehicle_type: metadata.vehicle_type.trim(),
    vehicle_category: metadata.vehicle_category.trim(),
  }
  const hasEvidence = Boolean(
    payload.vehicle_brand ||
      payload.vehicle_model ||
      payload.vin ||
      payload.registration ||
      payload.vehicle_year ||
      payload.vehicle_variant ||
      payload.vehicle_type ||
      payload.vehicle_category,
  )
  return hasEvidence ? payload : undefined
}

function Field({
  id,
  label,
  value,
  onChange,
}: {
  id: keyof IdentityMetadata
  label: string
  value: string
  onChange: (value: string) => void
}) {
  return (
    <div className="space-y-2">
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </div>
  )
}
