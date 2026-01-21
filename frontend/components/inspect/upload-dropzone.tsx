"use client"

import React from "react"

import { useState, useCallback } from "react"
import { Upload, Film, X, FileVideo, CheckCircle2, AlertCircle } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { cn } from "@/lib/utils"
import { uploadVideo } from "@/lib/api"

interface UploadedFile {
  id: string
  name: string
  size: number
  progress: number
  status: "uploading" | "processing" | "complete" | "error"
  jobId?: string
  error?: string
}

interface UploadDropzoneProps {
  onFilesUploaded: (files: UploadedFile[]) => void
}

export function UploadDropzone({ onFilesUploaded }: UploadDropzoneProps) {
  const [isDragging, setIsDragging] = useState(false)
  const [files, setFiles] = useState<UploadedFile[]>([])

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(true)
  }, [])

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
  }, [])

  const handleUpload = useCallback(async (file: File, odometerImage?: File | null) => {
    const newFile: UploadedFile = {
      id: Math.random().toString(36).substring(7),
      name: file.name,
      size: file.size,
      progress: 0,
      status: "uploading",
    }

    setFiles((prev) => [...prev, newFile])

    try {
      const result = await uploadVideo(file, odometerImage, (progress) => {
        setFiles((prev) =>
          prev.map((f) => (f.id === newFile.id ? { ...f, progress } : f))
        )
      })

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
  }, [onFilesUploaded])

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

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024 * 1024) {
      return `${(bytes / 1024).toFixed(1)} KB`
    }
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  return (
    <div className="space-y-4">
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={cn(
          "relative flex min-h-[300px] cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed transition-all",
          isDragging
            ? "border-primary bg-primary/5"
            : "border-border bg-secondary/30 hover:border-primary/50 hover:bg-secondary/50"
        )}
      >
        <input
          type="file"
          accept="video/*"
          multiple
          onChange={handleFileInput}
          className="absolute inset-0 cursor-pointer opacity-0"
        />

        <div className="flex flex-col items-center gap-4 p-8 text-center">
          <div className="flex h-16 w-16 items-center justify-center rounded-full bg-primary/10">
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
            <span>4K supported</span>
          </div>

          <Button variant="outline" className="mt-2 bg-transparent">
            Browse Files
          </Button>
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
