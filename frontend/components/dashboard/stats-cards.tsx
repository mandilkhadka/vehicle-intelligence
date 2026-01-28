"use client"

import { Car, FileCheck, AlertTriangle, Clock } from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { MetricsResponse } from "@/lib/api"

interface StatsCardsProps {
  metrics?: MetricsResponse | null
  isLoading?: boolean
}

export function StatsCards({ metrics, isLoading = false }: StatsCardsProps) {
  const stats = {
    totalInspections: metrics?.summary.totalInspections ?? 0,
    vehiclesAnalyzed: metrics?.summary.uniqueVehicles ?? 0,
    issuesDetected: metrics?.summary.totalIssues ?? 0,
    avgProcessingTime: metrics?.summary.avgProcessingTime
      ? `${metrics.summary.avgProcessingTime}s`
      : "0s",
  }

  const statsData = [
    {
      title: "Total Inspections",
      value: stats.totalInspections.toLocaleString(),
      icon: FileCheck,
      description: "in selected period",
    },
    {
      title: "Vehicles Analyzed",
      value: stats.vehiclesAnalyzed.toLocaleString(),
      icon: Car,
      description: "unique vehicles",
    },
    {
      title: "Issues Detected",
      value: stats.issuesDetected.toLocaleString(),
      icon: AlertTriangle,
      description: "total issues",
    },
    {
      title: "Avg. Processing Time",
      value: stats.avgProcessingTime,
      icon: Clock,
      description: "per inspection",
    },
  ]

  if (isLoading) {
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
              <div className="mt-1 text-sm text-muted-foreground">
                {stat.description}
              </div>
            </CardContent>
          </Card>
        )
      })}
    </div>
  )
}
