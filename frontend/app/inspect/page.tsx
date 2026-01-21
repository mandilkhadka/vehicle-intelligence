"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { Header } from "@/components/header"
import { Sidebar } from "@/components/sidebar"
import { UploadDropzone } from "@/components/inspect/upload-dropzone"
import { InspectionOptions } from "@/components/inspect/inspection-options"
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

  const handleFilesUploaded = (files: UploadedFile[]) => {
    setUploadedFiles(files)
  }

  const handleStartInspection = () => {
    const completedFile = uploadedFiles.find((f) => f.status === "complete" && f.jobId)
    if (!completedFile?.jobId) return

    setIsStarting(true)
    // Redirect to job status page to monitor processing
    router.push(`/job/${completedFile.jobId}`)
  }

  return (
    <div className="min-h-screen bg-background">
      <Header />
      <div className="flex">
        <Sidebar />
        <main className="flex-1 overflow-auto">
          <div className="p-6">
            <div className="mb-6 flex items-center justify-between">
              <div>
                <h1 className="text-2xl font-bold tracking-tight">
                  New Inspection
                </h1>
                <p className="text-muted-foreground">
                  Upload a 360° vehicle video for AI analysis
                </p>
              </div>
              <Button
                onClick={handleStartInspection}
                disabled={!uploadedFiles.some((f) => f.status === "complete" && f.jobId) || isStarting}
                className="gap-2"
              >
                {isStarting ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Starting...
                  </>
                ) : (
                  <>
                    Start Inspection
                    <ArrowRight className="h-4 w-4" />
                  </>
                )}
              </Button>
            </div>

            <div className="grid gap-6 lg:grid-cols-3">
              <div className="lg:col-span-2">
                <UploadDropzone onFilesUploaded={handleFilesUploaded} />
              </div>
              <div>
                <InspectionOptions />
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>
  )
}
