"use client"

import { useState, useEffect, Suspense } from "react"
import { useSearchParams } from "next/navigation"
import Link from "next/link"
import Image from "next/image"
import { Header } from "@/components/header"
import { Sidebar } from "@/components/sidebar"
import { VehicleInfo } from "@/components/results/vehicle-info"
import { DamageReport } from "@/components/results/damage-report"
import { ExhaustAnalysis } from "@/components/results/exhaust-analysis"
import { InspectionSummary } from "@/components/results/inspection-summary"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { ArrowLeft, Plus, ZoomIn, Loader2 } from "lucide-react"
import { getInspection, BACKEND_BASE_URL } from "@/lib/api"

function InspectionResultsContent() {
  const searchParams = useSearchParams()
  const inspectionId = searchParams.get("id")
  const [inspection, setInspection] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const fetchInspection = async () => {
      if (!inspectionId) {
        setError("No inspection ID provided")
        setLoading(false)
        return
      }

      try {
        const data = await getInspection(inspectionId)
        setInspection(data)
      } catch (err: any) {
        setError("Failed to load inspection data")
        console.error(err)
      } finally {
        setLoading(false)
      }
    }

    fetchInspection()
  }, [inspectionId])

  if (loading) {
    return (
      <div className="min-h-screen bg-background">
        <Header />
        <div className="flex">
          <Sidebar />
          <main className="flex-1 overflow-auto">
            <div className="p-6 flex items-center justify-center min-h-[60vh]">
              <div className="text-center">
                <Loader2 className="h-8 w-8 animate-spin mx-auto text-primary mb-4" />
                <p className="text-muted-foreground">Loading inspection data...</p>
              </div>
            </div>
          </main>
        </div>
      </div>
    )
  }

  if (error || !inspection) {
    return (
      <div className="min-h-screen bg-background">
        <Header />
        <div className="flex">
          <Sidebar />
          <main className="flex-1 overflow-auto">
            <div className="p-6 flex items-center justify-center min-h-[60vh]">
              <div className="text-center">
                <p className="text-destructive mb-4">{error || "Inspection not found"}</p>
                <Button asChild>
                  <Link href="/inspect">Go back</Link>
                </Button>
              </div>
            </div>
          </main>
        </div>
      </div>
    )
  }

  // Parse JSON fields if they're strings
  const vehicleInfo =
    typeof inspection.vehicle_info === "string"
      ? JSON.parse(inspection.vehicle_info)
      : inspection.vehicle_info || {
          type: inspection.vehicle_type,
          brand: inspection.vehicle_brand,
          model: inspection.vehicle_model,
          confidence: inspection.vehicle_confidence,
        }

  const vehicleData = {
    brand: vehicleInfo.brand || inspection.vehicle_brand || "Unknown",
    model: vehicleInfo.model || inspection.vehicle_model || "Unknown",
    year: vehicleInfo.year || new Date().getFullYear(),
    type: vehicleInfo.type || inspection.vehicle_type || "Vehicle",
    odometer: inspection.odometer_value || "N/A",
    fuelType: vehicleInfo.fuelType || "Unknown",
    transmission: vehicleInfo.transmission || "Unknown",
    vin: vehicleInfo.vin || "N/A",
    confidence: vehicleInfo.confidence || inspection.vehicle_confidence || 0,
    image: vehicleInfo.image || "/placeholder.svg",
  }

  const damage =
    typeof inspection.damage_summary === "string"
      ? JSON.parse(inspection.damage_summary)
      : inspection.damage_summary || {
          scratches: { count: inspection.scratches_detected || 0 },
          dents: { count: inspection.dents_detected || 0 },
          rust: { count: inspection.rust_detected || 0 },
          severity: inspection.damage_severity || "low",
        }

  const damageData = [
    ...(damage.scratches?.count > 0
      ? [
          {
            id: "SCRATCH",
            type: "Scratch",
            severity: damage.severity === "high" ? ("high" as const) : damage.severity === "medium" ? ("medium" as const) : ("low" as const),
            location: "Body",
            description: `${damage.scratches.count} scratch(es) detected`,
            estimatedCost: "$" + (damage.scratches.count * 100),
          },
        ]
      : []),
    ...(damage.dents?.count > 0
      ? [
          {
            id: "DENT",
            type: "Dent",
            severity: damage.severity === "high" ? ("high" as const) : damage.severity === "medium" ? ("medium" as const) : ("low" as const),
            location: "Body",
            description: `${damage.dents.count} dent(s) detected`,
            estimatedCost: "$" + (damage.dents.count * 200),
          },
        ]
      : []),
    ...(damage.rust?.count > 0
      ? [
          {
            id: "RUST",
            type: "Rust",
            severity: "high" as const,
            location: "Body",
            description: `${damage.rust.count} rust spot(s) detected`,
            estimatedCost: "$" + (damage.rust.count * 300),
          },
        ]
      : []),
  ]

  const exhaustData = {
    classification: (inspection.exhaust_type === "modified" ? ("modified" as const) : ("stock" as const)),
    confidence: inspection.exhaust_confidence || 0,
    details: inspection.exhaust_type === "modified" ? ["Aftermarket exhaust detected"] : ["Stock exhaust system"],
    modifications: inspection.exhaust_type === "modified" ? ["Aftermarket Exhaust"] : [],
  }

  const inspectionData = {
    id: inspection.id || inspectionId || "N/A",
    date: inspection.created_at ? new Date(inspection.created_at).toLocaleDateString() : new Date().toLocaleDateString(),
    duration: "N/A",
    status: "passed" as const,
    score: Math.round((vehicleData.confidence + (inspection.exhaust_confidence || 0)) / 2),
    aiModel: "VIP-Advanced v3.2",
  }

  const frames =
    typeof inspection.extracted_frames === "string"
      ? JSON.parse(inspection.extracted_frames)
      : inspection.extracted_frames || []
  return (
    <div className="min-h-screen bg-background">
      <Header />
      <div className="flex">
        <Sidebar />
        <main className="flex-1 overflow-auto">
          <div className="p-6">
            <div className="mb-6 flex items-center justify-between">
              <div className="flex items-center gap-4">
                <Button variant="ghost" size="icon" asChild>
                  <Link href="/inspect">
                    <ArrowLeft className="h-5 w-5" />
                  </Link>
                </Button>
                <div>
                  <h1 className="text-2xl font-bold tracking-tight">
                    Inspection Results
                  </h1>
                  <p className="text-muted-foreground">
                    {vehicleData.year} {vehicleData.brand} {vehicleData.model}
                  </p>
                </div>
              </div>
              <Button className="gap-2" asChild>
                <Link href="/inspect">
                  <Plus className="h-4 w-4" />
                  New Inspection
                </Link>
              </Button>
            </div>

            {/* Vehicle Image Preview */}
            {frames.length > 0 && (
              <Card className="mb-6 overflow-hidden">
                <CardContent className="p-0">
                  <div className="relative aspect-video w-full">
                    <Image
                      src={`${BACKEND_BASE_URL}/uploads/${frames[0]}`}
                      alt={`${vehicleData.year} ${vehicleData.brand} ${vehicleData.model}`}
                      fill
                      className="object-cover"
                      priority
                      unoptimized
                    />
                    <div className="absolute inset-0 bg-gradient-to-t from-background/80 to-transparent" />
                    <div className="absolute bottom-4 left-4 right-4 flex items-end justify-between">
                      <div>
                        <h2 className="text-2xl font-bold text-foreground">
                          {vehicleData.year} {vehicleData.brand} {vehicleData.model}
                        </h2>
                        <p className="text-muted-foreground">{vehicleData.type}</p>
                      </div>
                      {frames.length > 1 && (
                        <Button variant="secondary" size="sm" className="gap-2">
                          <ZoomIn className="h-4 w-4" />
                          View Gallery ({frames.length} frames)
                        </Button>
                      )}
                    </div>
                  </div>
                </CardContent>
              </Card>
            )}

            <div className="grid gap-6 lg:grid-cols-3">
              <div className="space-y-6 lg:col-span-2">
                <VehicleInfo vehicle={vehicleData} />
                <DamageReport damages={damageData} />
              </div>
              <div className="space-y-6">
                <InspectionSummary inspection={inspectionData} />
                <ExhaustAnalysis analysis={exhaustData} />
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>
  )
}

export default function InspectionResultsPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen bg-background">
        <Header />
        <div className="flex">
          <Sidebar />
          <main className="flex-1 overflow-auto">
            <div className="p-6 flex items-center justify-center min-h-[60vh]">
              <div className="text-center">
                <Loader2 className="h-8 w-8 animate-spin mx-auto text-primary mb-4" />
                <p className="text-muted-foreground">Loading...</p>
              </div>
            </div>
          </main>
        </div>
      </div>
    }>
      <InspectionResultsContent />
    </Suspense>
  )
}
