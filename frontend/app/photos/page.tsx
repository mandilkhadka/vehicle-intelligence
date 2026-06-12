"use client"

import { useCallback } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { AppShell } from "@/components/app-shell"
import { PageHeader } from "@/components/page-header"
import { PhotoUpload } from "@/components/photos/photo-upload"
import { Button } from "@/components/ui/button"
import { Callout } from "@/components/ui/callout"
import { Film } from "lucide-react"

export default function PhotosPage() {
  const router = useRouter()

  // Processing starts server-side the moment the upload lands, so take the
  // user straight to the job progress page instead of making them click.
  const handleUploaded = useCallback(
    (jobId: string) => {
      router.push(`/job/${jobId}`)
    },
    [router],
  )

  return (
    <AppShell>
      <div className="mx-auto max-w-5xl p-4 sm:p-6 lg:p-8">
        <PageHeader
          title="Photo inspection"
          description="Upload up to 24 photos of the vehicle. An odometer photo is optional."
        >
          <Button variant="outline" asChild className="gap-2">
            <Link href="/inspect">
              <Film className="h-4 w-4" />
              Upload a video instead
            </Link>
          </Button>
        </PageHeader>

        <div className="space-y-4">
          <Callout variant="info">
            For best results, cover all four sides of the vehicle plus the
            corners. Including a dashboard photo lets the system read the
            odometer.
          </Callout>

          <PhotoUpload onUploaded={handleUploaded} />
        </div>
      </div>
    </AppShell>
  )
}
