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
import { getApiErrorMessage } from "@/lib/api-error"
import { RefreshCw } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Callout } from "@/components/ui/callout"

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
  const [fetchError, setFetchError] = useState<string | null>(null)

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
      setFetchError(null)
    } catch (error) {
      console.error("Failed to fetch metrics:", error)
      // Keep existing data on background-refresh errors, but surface the
      // failure when we have nothing to show yet (first load).
      setFetchError(getApiErrorMessage(error, "Failed to load metrics"))
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
        <PageHeader title="Dashboard">
          <DateFilter
            startDate={dateRange.start}
            endDate={dateRange.end}
            onRangeChange={handleRangeChange}
          />
          {lastUpdated && (
            <span className="text-xs text-muted-foreground">
              Updated {format(lastUpdated, "h:mm a")}
            </span>
          )}
          <Button
            variant="ghost"
            size="icon"
            onClick={() => fetchMetrics(true)}
            disabled={isRefreshing || isLoading}
            aria-label="Refresh metrics"
            title="Refresh metrics"
          >
            <RefreshCw className={isRefreshing ? "h-4 w-4 animate-spin" : "h-4 w-4"} />
          </Button>
        </PageHeader>

        <div className="space-y-6">
          {fetchError && metrics === null && !isLoading && (
            <Callout variant="destructive">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <span>{fetchError}</span>
                <Button variant="outline" size="sm" onClick={() => fetchMetrics(true)}>
                  Retry
                </Button>
              </div>
            </Callout>
          )}
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
