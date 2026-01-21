"use client"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { FileText, Download, Share2, CheckCircle2, XCircle, Clock } from "lucide-react"

interface InspectionSummaryProps {
  inspection: {
    id: string
    date: string
    duration: string
    status: "passed" | "failed" | "needs_review"
    score: number
    aiModel: string
  }
}

export function InspectionSummary({ inspection }: InspectionSummaryProps) {
  const getStatusInfo = () => {
    switch (inspection.status) {
      case "passed":
        return {
          label: "Passed",
          icon: CheckCircle2,
          className: "bg-emerald-500/10 text-emerald-500",
        }
      case "failed":
        return {
          label: "Failed",
          icon: XCircle,
          className: "bg-destructive/10 text-destructive",
        }
      case "needs_review":
        return {
          label: "Needs Review",
          icon: Clock,
          className: "bg-accent/10 text-accent",
        }
    }
  }

  const statusInfo = getStatusInfo()
  const StatusIcon = statusInfo.icon

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <FileText className="h-5 w-5 text-primary" />
            Inspection Summary
          </CardTitle>
          <Badge className={statusInfo.className}>
            <StatusIcon className="mr-1 h-3 w-3" />
            {statusInfo.label}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center justify-center">
          <div className="relative flex h-32 w-32 items-center justify-center">
            <svg className="h-full w-full -rotate-90">
              <circle
                cx="64"
                cy="64"
                r="56"
                fill="none"
                stroke="currentColor"
                strokeWidth="8"
                className="text-secondary"
              />
              <circle
                cx="64"
                cy="64"
                r="56"
                fill="none"
                stroke="currentColor"
                strokeWidth="8"
                strokeDasharray={`${(inspection.score / 100) * 352} 352`}
                strokeLinecap="round"
                className={
                  inspection.score >= 80
                    ? "text-emerald-500"
                    : inspection.score >= 60
                      ? "text-accent"
                      : "text-destructive"
                }
              />
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-3xl font-bold">{inspection.score}</span>
              <span className="text-xs text-muted-foreground">Score</span>
            </div>
          </div>
        </div>

        <div className="space-y-2 rounded-lg bg-secondary/50 p-3">
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Inspection ID</span>
            <span className="font-mono">{inspection.id}</span>
          </div>
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Date</span>
            <span>{inspection.date}</span>
          </div>
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Processing Time</span>
            <span>{inspection.duration}</span>
          </div>
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">AI Model</span>
            <span>{inspection.aiModel}</span>
          </div>
        </div>

        <div className="flex gap-2">
          <Button className="flex-1 gap-2">
            <Download className="h-4 w-4" />
            Export PDF
          </Button>
          <Button variant="outline" size="icon">
            <Share2 className="h-4 w-4" />
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
