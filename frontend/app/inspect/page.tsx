"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { Header } from "@/components/header"
import { Sidebar } from "@/components/sidebar"
import { UploadDropzone } from "@/components/inspect/upload-dropzone"
import { Button } from "@/components/ui/button"
import { ArrowRight, Loader2 } from "lucide-react"

interface UploadedFile {
  id: string
  name: string
  size: number
  progress: number
  status: "uploading" | "processing" | "complete" | "error"
  jobId?: string
}

export default function InspectPage() {
  const router = useRouter()
  const [uploadedFiles, setUploadedFiles] = useState<UploadedFile[]>([])
  const [isStarting, setIsStarting] = useState(false)

  const completedFile = uploadedFiles.find((f) => f.status === "complete" && f.jobId)
  const canStart = Boolean(completedFile?.jobId) && !isStarting

  const handleStartInspection = () => {
    if (!completedFile?.jobId) return
    setIsStarting(true)
    router.push(`/job/${completedFile.jobId}`)
  }

  return (
    <div className="min-h-screen bg-background">
      <Header />
      <div className="flex">
        <Sidebar />
        <main className="flex-1 overflow-auto">
          <div className="mx-auto max-w-3xl p-6">
            <div className="mb-6">
              <h1 className="text-2xl font-bold tracking-tight">New Inspection</h1>
              <p className="text-muted-foreground">
                Upload a 360° vehicle video. Optionally include a clear odometer photo.
              </p>
            </div>

            <UploadDropzone onFilesUploaded={setUploadedFiles} />

            <div className="mt-6 flex justify-end">
              <Button onClick={handleStartInspection} disabled={!canStart} className="gap-2">
                {isStarting ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Starting…
                  </>
                ) : (
                  <>
                    Start Inspection
                    <ArrowRight className="h-4 w-4" />
                  </>
                )}
              </Button>
            </div>
          </div>
        </main>
      </div>
    </div>
  )
}
