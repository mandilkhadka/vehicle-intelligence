"use client"

import React, { useCallback, useEffect, useRef, useState } from "react"
import { Gauge, ImagePlus, Upload, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Callout } from "@/components/ui/callout"
import { Progress } from "@/components/ui/progress"
import { cn } from "@/lib/utils"
import { uploadPhotos } from "@/lib/api"
import { getApiErrorMessage } from "@/lib/api-error"
import {
  EMPTY_IDENTITY,
  IdentityFields,
  identityPayload,
  type IdentityMetadata,
} from "@/components/inspect/identity-fields"

export const MAX_PHOTOS = 24
export const ACCEPTED_EXTENSIONS = [".jpg", ".jpeg", ".png", ".webp"]
const ACCEPT_ATTR = ACCEPTED_EXTENSIONS.join(",")

interface SelectedPhoto {
  id: string
  file: File
  previewUrl: string
}

interface PhotoUploadProps {
  /** Called with the job ID after the backend accepts the upload. */
  onUploaded: (jobId: string) => void
}

function hasAllowedExtension(name: string): boolean {
  const lower = name.toLowerCase()
  return ACCEPTED_EXTENSIONS.some((ext) => lower.endsWith(ext))
}

export function PhotoUpload({ onUploaded }: PhotoUploadProps) {
  const [photos, setPhotos] = useState<SelectedPhoto[]>([])
  const [odometerPhoto, setOdometerPhoto] = useState<SelectedPhoto | null>(null)
  const [validationError, setValidationError] = useState<string | null>(null)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [isDragging, setIsDragging] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const [progress, setProgress] = useState(0)
  const [identityMetadata, setIdentityMetadata] = useState<IdentityMetadata>(EMPTY_IDENTITY)

  const photoInputRef = useRef<HTMLInputElement | null>(null)
  const odometerInputRef = useRef<HTMLInputElement | null>(null)
  // Every object URL ever created, so unmount can revoke whatever is left.
  const objectUrlsRef = useRef<Set<string>>(new Set())

  useEffect(() => {
    const urls = objectUrlsRef.current
    return () => {
      urls.forEach((url) => URL.revokeObjectURL(url))
      urls.clear()
    }
  }, [])

  const makePreview = useCallback((file: File): SelectedPhoto => {
    const previewUrl = URL.createObjectURL(file)
    objectUrlsRef.current.add(previewUrl)
    return {
      id: Math.random().toString(36).substring(7),
      file,
      previewUrl,
    }
  }, [])

  const releasePreview = useCallback((previewUrl: string) => {
    URL.revokeObjectURL(previewUrl)
    objectUrlsRef.current.delete(previewUrl)
  }, [])

  const addPhotos = useCallback(
    (incoming: File[]) => {
      const invalid = incoming.filter((f) => !hasAllowedExtension(f.name))
      const valid = incoming.filter((f) => hasAllowedExtension(f.name))

      const remaining = Math.max(0, MAX_PHOTOS - photos.length)
      const accepted = valid.slice(0, remaining)
      const overflow = valid.length - accepted.length

      const messages: string[] = []
      if (invalid.length > 0) {
        messages.push(
          `Unsupported file type: ${invalid.map((f) => f.name).join(", ")}. ` +
            `Use .jpg, .jpeg, .png, or .webp.`,
        )
      }
      if (overflow > 0) {
        messages.push(
          `Maximum ${MAX_PHOTOS} photos per inspection — ${overflow} photo${overflow === 1 ? " was" : "s were"} not added.`,
        )
      }
      setValidationError(messages.length > 0 ? messages.join(" ") : null)

      if (accepted.length > 0) {
        setPhotos((prev) => [...prev, ...accepted.map(makePreview)])
      }
    },
    [photos.length, makePreview],
  )

  const removePhoto = useCallback(
    (id: string) => {
      setPhotos((prev) => {
        const target = prev.find((p) => p.id === id)
        if (target) releasePreview(target.previewUrl)
        return prev.filter((p) => p.id !== id)
      })
    },
    [releasePreview],
  )

  const setOdometerFile = useCallback(
    (file: File | null) => {
      setOdometerPhoto((prev) => {
        if (prev) releasePreview(prev.previewUrl)
        return file ? makePreview(file) : null
      })
    },
    [makePreview, releasePreview],
  )

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setIsDragging(false)
      addPhotos(Array.from(e.dataTransfer.files))
    },
    [addPhotos],
  )

  const handlePhotoInput = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      if (e.target.files) {
        addPhotos(Array.from(e.target.files))
      }
      // Allow re-selecting the same files after removal.
      e.target.value = ""
    },
    [addPhotos],
  )

  const handleOdometerInput = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0]
      if (file) {
        if (!hasAllowedExtension(file.name)) {
          setValidationError(
            `Unsupported file type: ${file.name}. Use .jpg, .jpeg, .png, or .webp.`,
          )
        } else {
          setOdometerFile(file)
        }
      }
      e.target.value = ""
    },
    [setOdometerFile],
  )

  const handleSubmit = useCallback(async () => {
    if (photos.length === 0 || isUploading) return
    setUploadError(null)
    setIsUploading(true)
    setProgress(0)
    try {
      const result = await uploadPhotos(
        photos.map((p) => p.file),
        odometerPhoto?.file ?? null,
        setProgress,
        identityPayload(identityMetadata),
      )
      onUploaded(result.jobId)
    } catch (error) {
      setUploadError(getApiErrorMessage(error, "Upload failed"))
      setIsUploading(false)
    }
  }, [photos, odometerPhoto, identityMetadata, isUploading, onUploaded])

  const openPhotoPicker = () => photoInputRef.current?.click()

  return (
    <div className="space-y-4">
      <div
        role="button"
        tabIndex={0}
        aria-label="Add vehicle photos"
        onClick={openPhotoPicker}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault()
            openPhotoPicker()
          }
        }}
        onDragOver={(e) => {
          e.preventDefault()
          setIsDragging(true)
        }}
        onDragLeave={(e) => {
          e.preventDefault()
          setIsDragging(false)
        }}
        onDrop={handleDrop}
        className={cn(
          "relative flex min-h-[220px] cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          isDragging
            ? "border-primary bg-primary/5"
            : "border-border bg-secondary/30 hover:border-primary/50 hover:bg-secondary/50",
        )}
      >
        <input
          ref={photoInputRef}
          type="file"
          accept={ACCEPT_ATTR}
          multiple
          onChange={handlePhotoInput}
          className="sr-only"
          tabIndex={-1}
          aria-hidden="true"
        />

        <div className="flex flex-col items-center gap-4 p-8 text-center">
          <div className="flex h-16 w-16 items-center justify-center rounded-lg bg-primary/10">
            <Upload className="h-8 w-8 text-primary" />
          </div>

          <div>
            <p className="text-lg font-semibold">Drop vehicle photos here</p>
            <p className="mt-1 text-sm text-muted-foreground">
              or click to browse from your computer
            </p>
          </div>

          <div className="flex items-center gap-4 text-xs text-muted-foreground">
            <span className="flex items-center gap-1">
              <ImagePlus className="h-3 w-3" />
              JPG, PNG, WebP
            </span>
            <span>Up to {MAX_PHOTOS} photos</span>
          </div>

          <Button
            variant="outline"
            className="mt-2 bg-transparent"
            onClick={(e) => {
              e.stopPropagation()
              openPhotoPicker()
            }}
          >
            Browse Files
          </Button>
        </div>
      </div>

      {validationError && (
        <Callout variant="warning">{validationError}</Callout>
      )}

      {photos.length > 0 && (
        <div className="space-y-3">
          <h3 className="text-sm font-medium">
            Selected photos ({photos.length}/{MAX_PHOTOS})
          </h3>
          <ul className="grid grid-cols-3 gap-3 sm:grid-cols-4 md:grid-cols-6">
            {photos.map((photo) => (
              <li
                key={photo.id}
                className="relative aspect-square overflow-hidden rounded-md border border-border bg-secondary/30"
              >
                {/* eslint-disable-next-line @next/next/no-img-element -- local blob preview; next/image cannot optimize object URLs */}
                <img
                  src={photo.previewUrl}
                  alt={photo.file.name}
                  className="h-full w-full object-cover"
                />
                <Button
                  variant="secondary"
                  size="icon"
                  className="absolute right-1 top-1 h-6 w-6"
                  aria-label={`Remove ${photo.file.name}`}
                  disabled={isUploading}
                  onClick={() => removePhoto(photo.id)}
                >
                  <X className="h-3 w-3" />
                </Button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="rounded-lg border border-border bg-card p-4">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-secondary">
            <Gauge className="h-5 w-5 text-primary" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium">Odometer photo (optional)</p>
            <p className="text-xs text-muted-foreground">
              A clear dashboard close-up improves the odometer reading.
            </p>
          </div>
          <input
            ref={odometerInputRef}
            type="file"
            accept={ACCEPT_ATTR}
            onChange={handleOdometerInput}
            className="sr-only"
            tabIndex={-1}
            aria-hidden="true"
          />
          {odometerPhoto ? (
            <div className="flex items-center gap-2">
              {/* eslint-disable-next-line @next/next/no-img-element -- local blob preview; next/image cannot optimize object URLs */}
              <img
                src={odometerPhoto.previewUrl}
                alt={odometerPhoto.file.name}
                className="h-10 w-10 rounded-md border border-border object-cover"
              />
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6"
                aria-label="Remove odometer photo"
                disabled={isUploading}
                onClick={() => setOdometerFile(null)}
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          ) : (
            <Button
              variant="outline"
              size="sm"
              onClick={() => odometerInputRef.current?.click()}
            >
              Add odometer photo
            </Button>
          )}
        </div>
      </div>

      <IdentityFields value={identityMetadata} onFieldChange={(field, value) =>
        setIdentityMetadata((prev) => ({ ...prev, [field]: value }))
      } />

      {uploadError && <Callout variant="destructive">{uploadError}</Callout>}

      {isUploading && (
        <div className="space-y-1">
          <p className="text-xs text-primary">Uploading {Math.round(progress)}%</p>
          <Progress value={progress} className="h-1" />
        </div>
      )}

      <div className="flex justify-end">
        <Button
          onClick={handleSubmit}
          disabled={photos.length === 0 || isUploading}
        >
          {isUploading
            ? "Uploading…"
            : `Start inspection (${photos.length} photo${photos.length === 1 ? "" : "s"})`}
        </Button>
      </div>
    </div>
  )
}
