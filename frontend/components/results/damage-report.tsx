"use client"

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { AlertTriangle, AlertCircle, Info, MapPin } from "lucide-react"

interface DamageItem {
  id: string
  type: string
  severity: "high" | "medium" | "low"
  location: string
  description: string
  estimatedCost: string
}

interface DamageReportProps {
  damages: DamageItem[]
}

function getSeverityBadge(severity: string) {
  switch (severity) {
    case "high":
      return (
        <Badge className="bg-destructive/10 text-destructive hover:bg-destructive/20">
          <AlertTriangle className="mr-1 h-3 w-3" />
          High
        </Badge>
      )
    case "medium":
      return (
        <Badge className="bg-accent/10 text-accent hover:bg-accent/20">
          <AlertCircle className="mr-1 h-3 w-3" />
          Medium
        </Badge>
      )
    case "low":
      return (
        <Badge className="bg-sky-500/10 text-sky-500 hover:bg-sky-500/20">
          <Info className="mr-1 h-3 w-3" />
          Low
        </Badge>
      )
    default:
      return <Badge variant="secondary">{severity}</Badge>
  }
}

export function DamageReport({ damages }: DamageReportProps) {
  const totalCost = damages.reduce((sum, d) => {
    const cost = parseInt(d.estimatedCost.replace(/[^0-9]/g, ""))
    return sum + cost
  }, 0)

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-accent" />
              Damage Detection
            </CardTitle>
            <CardDescription>
              {damages.length} issue{damages.length !== 1 ? "s" : ""} detected
            </CardDescription>
          </div>
          <div className="text-right">
            <p className="text-sm text-muted-foreground">Est. Repair Cost</p>
            <p className="text-xl font-bold text-accent">
              ${totalCost.toLocaleString()}
            </p>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {damages.map((damage) => (
            <div
              key={damage.id}
              className="rounded-lg border border-border bg-secondary/30 p-4"
            >
              <div className="flex items-start justify-between">
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <h4 className="font-semibold">{damage.type}</h4>
                    {getSeverityBadge(damage.severity)}
                  </div>
                  <div className="flex items-center gap-1 text-sm text-muted-foreground">
                    <MapPin className="h-3 w-3" />
                    {damage.location}
                  </div>
                  <p className="text-sm text-muted-foreground">
                    {damage.description}
                  </p>
                </div>
                <div className="text-right">
                  <p className="text-sm text-muted-foreground">Est. Cost</p>
                  <p className="font-semibold">{damage.estimatedCost}</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
