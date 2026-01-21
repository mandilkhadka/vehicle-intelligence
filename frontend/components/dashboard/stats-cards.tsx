"use client"

import { useEffect, useState } from "react"
import { Car, FileCheck, AlertTriangle, Clock } from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { getInspections } from "@/lib/api"
import { Loader2 } from "lucide-react"

const sampleInspections = [
  {
    id: "insp-001",
    vehicle: "KTM superduke 1290",
    brand: "KTM",
    model: "Duke 390",
    issues: 2,
  },
  {
    id: "insp-002",
    vehicle: "Toyota Alphard",
    brand: "Toyota",
    model: "Alphard",
    issues: 0,
  },
  {
    id: "insp-003",
    vehicle: "Kawasaki ZX-10R",
    brand: "Kawasaki",
    model: "ZX-10R",
    issues: 1,
  },
  {
    id: "insp-004",
    vehicle: "KTM",
    brand: "KTM",
    model: "LC8",
    issues: 0,
  },
  {
    id: "insp-005",
    vehicle: "Honda CBR 600",
    brand: "Honda",
    model: "CBR 600",
    issues: 3,
  },
]

export function StatsCards() {
  const [stats, setStats] = useState({
    totalInspections: 0,
    vehiclesAnalyzed: 0,
    issuesDetected: 0,
    avgProcessingTime: "0s",
  })
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const inspections = await getInspections()
        
        const uniqueVehicles = new Set<string>()
        let totalIssues = 0

        inspections.forEach((insp: any) => {
          const vehicleInfo =
            typeof insp.vehicle_info === "string"
              ? JSON.parse(insp.vehicle_info)
              : insp.vehicle_info || {}
          
          const vehicleKey = `${vehicleInfo.brand || insp.vehicle_brand || "Unknown"}-${vehicleInfo.model || insp.vehicle_model || "Unknown"}`
          uniqueVehicles.add(vehicleKey)

          const damage =
            typeof insp.damage_summary === "string"
              ? JSON.parse(insp.damage_summary)
              : insp.damage_summary || {}
          
          totalIssues +=
            (damage.scratches?.count || 0) +
            (damage.dents?.count || 0) +
            (damage.rust?.count || 0)
        })

        // Add sample inspections data
        sampleInspections.forEach((sample) => {
          const vehicleKey = `${sample.brand}-${sample.model}`
          uniqueVehicles.add(vehicleKey)
          totalIssues += sample.issues
        })

        const totalCount = inspections.length + sampleInspections.length
        const processingTimes = [2.1, 2.3, 2.5, 2.2, 2.4] // Sample processing times in seconds
        const avgTime = (processingTimes.reduce((a, b) => a + b, 0) / processingTimes.length).toFixed(1)

        setStats({
          totalInspections: totalCount,
          vehiclesAnalyzed: uniqueVehicles.size,
          issuesDetected: totalIssues,
          avgProcessingTime: `${avgTime}s`,
        })
      } catch (err) {
        console.error("Failed to fetch stats:", err)
        // Calculate stats from sample data only
        const uniqueVehicles = new Set<string>()
        let totalIssues = 0
        
        sampleInspections.forEach((sample) => {
          const vehicleKey = `${sample.brand}-${sample.model}`
          uniqueVehicles.add(vehicleKey)
          totalIssues += sample.issues
        })

        const processingTimes = [2.1, 2.3, 2.5, 2.2, 2.4]
        const avgTime = (processingTimes.reduce((a, b) => a + b, 0) / processingTimes.length).toFixed(1)

        setStats({
          totalInspections: sampleInspections.length,
          vehiclesAnalyzed: uniqueVehicles.size,
          issuesDetected: totalIssues,
          avgProcessingTime: `${avgTime}s`,
        })
      } finally {
        setLoading(false)
      }
    }

    fetchStats()
  }, [])

  const statsData = [
    {
      title: "Total Inspections",
      value: stats.totalInspections.toLocaleString(),
      change: "+0%",
      changeType: "positive" as const,
      icon: FileCheck,
      description: "all time",
    },
    {
      title: "Vehicles Analyzed",
      value: stats.vehiclesAnalyzed.toLocaleString(),
      change: "+0%",
      changeType: "positive" as const,
      icon: Car,
      description: "unique vehicles",
    },
    {
      title: "Issues Detected",
      value: stats.issuesDetected.toLocaleString(),
      change: "+0%",
      changeType: "negative" as const,
      icon: AlertTriangle,
      description: "total issues",
    },
    {
      title: "Avg. Processing Time",
      value: stats.avgProcessingTime,
      change: "+0%",
      changeType: "positive" as const,
      icon: Clock,
      description: "per inspection",
    },
  ]

  if (loading) {
    return (
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {[1, 2, 3, 4].map((i) => (
          <Card key={i} className="overflow-hidden">
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <div className="h-4 w-24 bg-secondary animate-pulse rounded" />
              <div className="rounded-md bg-secondary p-2 h-8 w-8 animate-pulse" />
            </CardHeader>
            <CardContent>
              <div className="h-8 w-16 bg-secondary animate-pulse rounded mb-2" />
              <div className="h-4 w-32 bg-secondary animate-pulse rounded" />
            </CardContent>
          </Card>
        ))}
      </div>
    )
  }

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
      {statsData.map((stat) => {
        const Icon = stat.icon
        return (
          <Card key={stat.title} className="overflow-hidden">
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                {stat.title}
              </CardTitle>
              <div className="rounded-md bg-secondary p-2">
                <Icon className="h-4 w-4 text-primary" />
              </div>
            </CardHeader>
            <CardContent>
              <div className="text-3xl font-bold">{stat.value}</div>
              <div className="mt-1 flex items-center gap-1 text-sm">
                <span
                  className={
                    stat.changeType === "positive"
                      ? "text-emerald-500"
                      : "text-red-500"
                  }
                >
                  {stat.change}
                </span>
                <span className="text-muted-foreground">{stat.description}</span>
              </div>
            </CardContent>
          </Card>
        )
      })}
    </div>
  )
}
