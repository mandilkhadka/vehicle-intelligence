"use client"

import { useEffect, useState } from "react"
import Image from "next/image"
import Link from "next/link"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { ArrowRight, ChevronRight, Loader2 } from "lucide-react"
import { getInspections, BACKEND_BASE_URL } from "@/lib/api"

function formatTimeAgo(date: Date): string {
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMs / 3600000)
  const diffDays = Math.floor(diffMs / 86400000)

  if (diffMins < 60) {
    return `${diffMins} minute${diffMins !== 1 ? "s" : ""} ago`
  } else if (diffHours < 24) {
    return `${diffHours} hour${diffHours !== 1 ? "s" : ""} ago`
  } else if (diffDays < 7) {
    return `${diffDays} day${diffDays !== 1 ? "s" : ""} ago`
  } else {
    return date.toLocaleDateString()
  }
}

function getStatusBadge(status: string) {
  switch (status) {
    case "completed":
      return <Badge className="bg-emerald-500/10 text-emerald-500 hover:bg-emerald-500/20">Completed</Badge>
    case "processing":
      return <Badge className="bg-primary/10 text-primary hover:bg-primary/20">Processing</Badge>
    case "failed":
      return <Badge className="bg-destructive/10 text-destructive hover:bg-destructive/20">Failed</Badge>
    default:
      return <Badge variant="secondary">{status}</Badge>
  }
}

const sampleInspections = [
  {
    id: "insp-001",
    vehicle: "KTM superduke 1290",
    brand: "KTM",
    status: "completed",
    issues: 2,
    date: new Date(Date.now() - 2 * 60 * 60 * 1000),
    dateString: "2 hours ago",
    odometer: "22,542 km",
    image: "/images/IMG_2075.PNG",
  },
  {
    id: "insp-002",
    vehicle: "Toyota Alphard",
    brand: "Toyota",
    status: "completed",
    issues: 0,
    date: new Date(Date.now() - 5 * 60 * 60 * 1000),
    dateString: "5 hours ago",
    odometer: "45,230 km",
    image: "/images/Screenshot_2026-01-21_at_21.43.00.png",
  },
  {
    id: "insp-003",
    vehicle: "Kawasaki ZX-10R",
    brand: "Kawasaki",
    status: "completed",
    issues: 1,
    date: new Date(Date.now() - 24 * 60 * 60 * 1000),
    dateString: "1 day ago",
    odometer: "18,750 km",
    image: "/images/IMG_9001.JPG",
  },
  {
    id: "insp-004",
    vehicle: "KTM",
    brand: "KTM",
    status: "completed",
    issues: 0,
    date: new Date(Date.now() - 2 * 24 * 60 * 60 * 1000),
    dateString: "2 days ago",
    odometer: "12,340 km",
    image: "/images/View_recent_photos.png",
  },
  {
    id: "insp-005",
    vehicle: "Honda CBR 600",
    brand: "Honda",
    status: "completed",
    issues: 3,
    date: new Date(Date.now() - 3 * 24 * 60 * 60 * 1000),
    dateString: "3 days ago",
    odometer: "8,920 km",
    image: "/images/cbr600.png",
  },
]

export function RecentInspections() {
  const [inspections, setInspections] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchInspections = async () => {
      try {
        const data = await getInspections()
        // Transform and sort by date, get most recent 5
        const transformed = data
          .map((insp: any) => {
            const vehicleInfo =
              typeof insp.vehicle_info === "string"
                ? JSON.parse(insp.vehicle_info)
                : insp.vehicle_info || {}
            
            const damage =
              typeof insp.damage_summary === "string"
                ? JSON.parse(insp.damage_summary)
                : insp.damage_summary || {}
            
            const issues =
              (damage.scratches?.count || 0) +
              (damage.dents?.count || 0) +
              (damage.rust?.count || 0)

            const frames =
              typeof insp.extracted_frames === "string"
                ? JSON.parse(insp.extracted_frames)
                : insp.extracted_frames || []

            return {
              id: insp.id,
              vehicle: `${vehicleInfo.brand || insp.vehicle_brand || "Unknown"} ${vehicleInfo.model || insp.vehicle_model || ""}`.trim(),
              brand: vehicleInfo.brand || insp.vehicle_brand || "Unknown",
              status: "completed",
              issues,
              date: insp.created_at ? new Date(insp.created_at) : new Date(),
              dateString: insp.created_at ? formatTimeAgo(new Date(insp.created_at)) : "Unknown",
              odometer: insp.odometer_value || "N/A",
              image: frames.length > 0 ? `${BACKEND_BASE_URL}/uploads/${frames[0]}` : null,
            }
          })
          .sort((a, b) => b.date.getTime() - a.date.getTime())
        
        const preparedSampleInspections = sampleInspections.map(sample => ({
          ...sample,
          dateString: formatTimeAgo(sample.date),
        }))
        
        const allInspections = [...transformed]
        if (allInspections.length < 5) {
          const samplesToAdd = preparedSampleInspections.slice(0, 5 - allInspections.length)
          allInspections.push(...samplesToAdd)
        }
        
        const sorted = allInspections
          .sort((a, b) => b.date.getTime() - a.date.getTime())
          .slice(0, 5)
        
        setInspections(sorted)
      } catch (err) {
        console.error("Failed to fetch inspections:", err)
        const preparedSampleInspections = sampleInspections.map(sample => ({
          ...sample,
          dateString: formatTimeAgo(sample.date),
        }))
        setInspections(preparedSampleInspections)
      } finally {
        setLoading(false)
      }
    }

    fetchInspections()
  }, [])

  return (
    <Card className="col-span-2">
      <CardHeader className="flex flex-row items-center justify-between">
        <div>
          <CardTitle>Recent Inspections</CardTitle>
          <CardDescription>Latest vehicle analysis results</CardDescription>
        </div>
        <Button variant="ghost" size="sm" className="gap-1" asChild>
          <Link href="/history">
            View all
            <ArrowRight className="h-4 w-4" />
          </Link>
        </Button>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-6 w-6 animate-spin text-primary" />
          </div>
        ) : inspections.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            No inspections yet
          </div>
        ) : (
          <div className="space-y-1">
            {inspections.map((inspection) => (
            <Link
              key={inspection.id}
              href={`/inspect/results?id=${inspection.id}`}
              className="group flex items-center justify-between rounded-lg p-3 transition-colors hover:bg-secondary/50 cursor-pointer"
            >
              <div className="flex items-center gap-4">
                {inspection.image ? (
                  <div className="relative h-12 w-16 overflow-hidden rounded-lg">
                    <Image
                      src={inspection.image || "/placeholder.svg"}
                      alt={inspection.vehicle}
                      fill
                      className="object-cover"
                    />
                  </div>
                ) : (
                  <div className="flex h-12 w-16 items-center justify-center rounded-lg bg-secondary text-xs font-medium text-muted-foreground">
                    {inspection.brand.slice(0, 2).toUpperCase()}
                  </div>
                )}
                <div>
                  <p className="font-medium">{inspection.vehicle}</p>
                  <p className="text-sm text-muted-foreground">
                    {inspection.id} · {inspection.odometer}
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-4">
                <div className="text-right">
                  {getStatusBadge(inspection.status)}
                  {inspection.status === "completed" && inspection.issues > 0 && (
                    <p className="mt-1 text-xs text-muted-foreground">
                      {inspection.issues} issue{inspection.issues > 1 ? "s" : ""} found
                    </p>
                  )}
                </div>
                <div className="text-right text-sm text-muted-foreground">
                  {inspection.dateString}
                </div>
                <ChevronRight className="h-4 w-4 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
              </div>
            </Link>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
