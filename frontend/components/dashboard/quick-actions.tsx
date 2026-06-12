"use client"

import Link from "next/link"
import { Upload, Images, ClipboardCheck, History } from "lucide-react"
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
    title: "Photo Inspection",
    description: "Upload vehicle photos instead of a video",
    icon: Images,
    href: "/photos",
    color: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
  },
  {
    title: "Review Detections",
    description: "Confirm or reject uncertain AI findings",
    icon: ClipboardCheck,
    href: "/review",
    color: "bg-amber-500/10 text-amber-600 dark:text-amber-400",
  },
  {
    title: "Inspection History",
    description: "Browse past inspections",
    icon: History,
    href: "/history",
    color: "bg-accent/10 text-accent",
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
