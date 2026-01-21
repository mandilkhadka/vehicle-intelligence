"use client"

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Progress } from "@/components/ui/progress"

const detectionTypes = [
  { type: "Scratches", count: 145, total: 342, color: "bg-chart-1" },
  { type: "Dents", count: 89, total: 342, color: "bg-chart-2" },
  { type: "Rust", count: 42, total: 342, color: "bg-chart-3" },
  { type: "Paint Chips", count: 38, total: 342, color: "bg-chart-4" },
  { type: "Exhaust Mods", count: 28, total: 342, color: "bg-chart-5" },
]

export function DetectionTypes() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Issue Breakdown</CardTitle>
        <CardDescription>Distribution by damage type</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {detectionTypes.map((item) => {
          const percentage = Math.round((item.count / item.total) * 100)
          return (
            <div key={item.type} className="space-y-2">
              <div className="flex items-center justify-between text-sm">
                <span>{item.type}</span>
                <span className="text-muted-foreground">
                  {item.count} <span className="text-xs">({percentage}%)</span>
                </span>
              </div>
              <div className="h-2 w-full overflow-hidden rounded-full bg-secondary">
                <div
                  className={`h-full rounded-full ${item.color} transition-all`}
                  style={{ width: `${percentage}%` }}
                />
              </div>
            </div>
          )
        })}
      </CardContent>
    </Card>
  )
}
