"use client"

import { useState, type ComponentType } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { AppShell } from "@/components/app-shell"
import { PageHeader } from "@/components/page-header"
import { UploadDropzone } from "@/components/inspect/upload-dropzone"
import { Button } from "@/components/ui/button"
import { ArrowRight, Camera, CheckCircle2, Film, Gauge, Loader2 } from "lucide-react"

interface UploadedFile {
  id: string
  name: string
  size: number
  progress: number
  status: "preflight" | "preflight_blocked" | "uploading" | "processing" | "complete" | "error"
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
    <AppShell>
      <div className="mx-auto max-w-5xl p-4 sm:p-6 lg:p-8">
        <PageHeader
          eyebrow="Capture"
          title="New Inspection"
          description="Upload a 360 degree walkaround video and, when available, a clear odometer photo for a stronger report."
        >
          <Button variant="outline" asChild className="gap-2">
            <Link href="/capture">
              <Camera className="h-4 w-4" />
              Record guided walkaround
            </Link>
          </Button>
        </PageHeader>

        <div className="grid gap-6 lg:grid-cols-[1fr_280px]">
          <div>
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

          <aside className="space-y-3">
            <ChecklistItem icon={Film} title="Video" text="MP4, MOV, or AVI walkaround." active />
            <ChecklistItem icon={Gauge} title="Odometer" text="Optional image improves reading confidence." />
            <ChecklistItem icon={CheckCircle2} title="Report" text="Results open automatically from the job page." />
          </aside>
        </div>
      </div>
    </AppShell>
  )
}

function ChecklistItem({
  icon: Icon,
  title,
  text,
  active = false,
}: {
  icon: ComponentType<{ className?: string }>
  title: string
  text: string
  active?: boolean
}) {
  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="flex items-start gap-3">
        <div className={active ? "rounded-md bg-primary/10 p-2 text-primary" : "rounded-md bg-secondary p-2 text-muted-foreground"}>
          <Icon className="h-4 w-4" />
        </div>
        <div>
          <p className="font-medium">{title}</p>
          <p className="mt-1 text-sm leading-5 text-muted-foreground">{text}</p>
        </div>
      </div>
    </div>
  )
}
