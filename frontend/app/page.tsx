"use client"

import { useEffect, useState, useCallback } from "react"
import { subDays, startOfDay, endOfDay, format } from "date-fns"
import { AppShell } from "@/components/app-shell"
import { PageHeader } from "@/components/page-header"
import { StatsCards } from "@/components/dashboard/stats-cards"
import { RecentInspections } from "@/components/dashboard/recent-inspections"
import { QuickActions } from "@/components/dashboard/quick-actions"
import { DateFilter } from "@/components/dashboard/date-filter"
import { AnalyticsSection } from "@/components/dashboard/analytics-section"
import { getMetrics, MetricsResponse } from "@/lib/api"
import { Activity, RefreshCw } from "lucide-react"

const AUTO_REFRESH_INTERVAL = 30000 // 30 seconds

export default function DashboardPage() {
  const [dateRange, setDateRange] = useState({
    start: startOfDay(subDays(new Date(), 29)),
    end: endOfDay(new Date()),
  })
  const [metrics, setMetrics] = useState<MetricsResponse | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)

  const fetchMetrics = useCallback(async (showRefreshIndicator = false) => {
    if (showRefreshIndicator) {
      setIsRefreshing(true)
    }

    try {
      const startDate = format(dateRange.start, "yyyy-MM-dd")
      const endDate = format(dateRange.end, "yyyy-MM-dd")
      const data = await getMetrics(startDate, endDate)
      setMetrics(data)
      setLastUpdated(new Date())
    } catch (error) {
      console.error("Failed to fetch metrics:", error)
      // Keep existing data on error
    } finally {
      setIsLoading(false)
      setIsRefreshing(false)
    }
  }, [dateRange])

  // Initial fetch and when date range changes
  useEffect(() => {
    setIsLoading(true)
    fetchMetrics()
  }, [fetchMetrics])

  // Auto-refresh with visibility handling
  useEffect(() => {
    let intervalId: NodeJS.Timeout | null = null

    const startRefresh = () => {
      intervalId = setInterval(() => {
        fetchMetrics(true)
      }, AUTO_REFRESH_INTERVAL)
    }

    const stopRefresh = () => {
      if (intervalId) {
        clearInterval(intervalId)
        intervalId = null
      }
    }

    const handleVisibilityChange = () => {
      if (document.hidden) {
        stopRefresh()
      } else {
        // Fetch immediately when tab becomes visible
        fetchMetrics(true)
        startRefresh()
      }
    }

    // Start auto-refresh
    startRefresh()
    document.addEventListener("visibilitychange", handleVisibilityChange)

    return () => {
      stopRefresh()
      document.removeEventListener("visibilitychange", handleVisibilityChange)
    }
  }, [fetchMetrics])

  const handleRangeChange = (start: Date, end: Date) => {
    setDateRange({ start, end })
  }

  return (
    <AppShell>
      <div className="p-4 sm:p-6 lg:p-8">
        <PageHeader
          eyebrow="Operations"
          title="Inspection Dashboard"
          description="Monitor vehicle uploads, model confidence, damage trends, and recent inspection outcomes from one console."
        >
          <div className="flex items-center gap-2 rounded-md border border-border bg-card px-3 py-2 text-xs text-muted-foreground">
            {isRefreshing ? (
              <RefreshCw className="h-4 w-4 animate-spin text-primary" />
            ) : (
              <Activity className="h-4 w-4 text-emerald-500" />
            )}
            <span className="hidden sm:inline">
              {lastUpdated ? `Updated ${format(lastUpdated, "h:mm a")}` : "Syncing metrics"}
            </span>
          </div>
        </PageHeader>

        <div className="mb-6 grid gap-4 xl:grid-cols-[1fr_auto] xl:items-center">
          <div className="rounded-lg border border-border bg-card p-4">
            <div className="grid gap-4 text-sm sm:grid-cols-3">
              <div>
                <p className="font-mono text-[11px] uppercase tracking-normal text-muted-foreground">
                  Analysis Window
                </p>
                <p className="mt-1 font-medium">
                  {format(dateRange.start, "MMM d")} - {format(dateRange.end, "MMM d, yyyy")}
                </p>
              </div>
              <div>
                <p className="font-mono text-[11px] uppercase tracking-normal text-muted-foreground">
                  Refresh Cadence
                </p>
                <p className="mt-1 font-medium">Every 30 seconds</p>
              </div>
              <div>
                <p className="font-mono text-[11px] uppercase tracking-normal text-muted-foreground">
                  Review Queue
                </p>
                <p className="mt-1 font-medium">
                  {metrics?.summary.totalInspections ?? 0} inspections
                </p>
              </div>
            </div>
          </div>

          <DateFilter
            startDate={dateRange.start}
            endDate={dateRange.end}
            onRangeChange={handleRangeChange}
          />
        </div>

        <div className="space-y-6">
          <StatsCards metrics={metrics} isLoading={isLoading} />

          <div className="grid gap-6 lg:grid-cols-3">
            <RecentInspections />
            <div className="space-y-6">
              <QuickActions />
              <AnalyticsSection metrics={metrics} isLoading={isLoading} />
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  )
}
