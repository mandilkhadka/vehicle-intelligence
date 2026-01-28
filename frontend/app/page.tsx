"use client"

import { useEffect, useState, useCallback } from "react"
import { subDays, startOfDay, endOfDay, format } from "date-fns"
import { Header } from "@/components/header"
import { Sidebar } from "@/components/sidebar"
import { StatsCards } from "@/components/dashboard/stats-cards"
import { RecentInspections } from "@/components/dashboard/recent-inspections"
import { QuickActions } from "@/components/dashboard/quick-actions"
import { DateFilter } from "@/components/dashboard/date-filter"
import { AnalyticsSection } from "@/components/dashboard/analytics-section"
import { getMetrics, MetricsResponse } from "@/lib/api"
import { RefreshCw } from "lucide-react"

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
    <div className="min-h-screen bg-background">
      <Header />
      <div className="flex">
        <Sidebar />
        <main className="flex-1 overflow-auto">
          <div className="p-6">
            <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
                <p className="text-muted-foreground">
                  AI-powered vehicle inspection overview
                </p>
              </div>
              <div className="flex items-center gap-2">
                {isRefreshing && (
                  <RefreshCw className="h-4 w-4 animate-spin text-muted-foreground" />
                )}
                {lastUpdated && (
                  <span className="text-xs text-muted-foreground hidden sm:inline">
                    Updated {format(lastUpdated, "h:mm a")}
                  </span>
                )}
              </div>
            </div>

            <div className="mb-6">
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
        </main>
      </div>
    </div>
  )
}
