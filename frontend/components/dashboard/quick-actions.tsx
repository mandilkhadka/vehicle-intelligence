"use client"

import Link from "next/link"
import { Upload, Camera, FileText, Gauge } from "lucide-react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

const actions = [
  {
    title: "Upload Video",
    description: "Start new 360° inspection",
    icon: Upload,
    href: "/inspect",
    color: "bg-primary/10 text-primary",
  },
  {
    title: "Quick Scan",
    description: "Single image analysis",
    icon: Camera,
    href: "/inspect?mode=quick",
    color: "bg-accent/10 text-accent",
  },
  {
    title: "Generate Report",
    description: "Export inspection data",
    icon: FileText,
    href: "/reports/new",
    color: "bg-emerald-500/10 text-emerald-500",
  },
  {
    title: "View Analytics",
    description: "Performance metrics",
    icon: Gauge,
    href: "/analytics",
    color: "bg-sky-500/10 text-sky-500",
  },
]

export function QuickActions() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Quick Actions</CardTitle>
        <CardDescription>Common tasks and shortcuts</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3">
        {actions.map((action) => {
          const Icon = action.icon
          return (
            <Link
              key={action.title}
              href={action.href}
              className="group flex items-center gap-3 rounded-lg border border-border bg-secondary/30 p-3 transition-all hover:border-primary/50 hover:bg-secondary/50"
            >
              <div className={`rounded-lg p-2 ${action.color}`}>
                <Icon className="h-4 w-4" />
              </div>
              <div>
                <p className="font-medium">{action.title}</p>
                <p className="text-sm text-muted-foreground">{action.description}</p>
              </div>
            </Link>
          )
        })}
      </CardContent>
    </Card>
  )
}
