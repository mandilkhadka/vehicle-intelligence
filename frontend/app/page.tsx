import { Header } from "@/components/header"
import { Sidebar } from "@/components/sidebar"
import { StatsCards } from "@/components/dashboard/stats-cards"
import { RecentInspections } from "@/components/dashboard/recent-inspections"
import { QuickActions } from "@/components/dashboard/quick-actions"
import { DetectionTypes } from "@/components/dashboard/detection-types"

export default function DashboardPage() {
  return (
    <div className="min-h-screen bg-background">
      <Header />
      <div className="flex">
        <Sidebar />
        <main className="flex-1 overflow-auto">
          <div className="p-6">
            <div className="mb-6">
              <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
              <p className="text-muted-foreground">
                AI-powered vehicle inspection overview
              </p>
            </div>

            <div className="space-y-6">
              <StatsCards />

              <div className="grid gap-6 lg:grid-cols-3">
                <RecentInspections />
                <div className="space-y-6">
                  <QuickActions />
                  <DetectionTypes />
                </div>
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>
  )
}
