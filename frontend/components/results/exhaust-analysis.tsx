"use client"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Wrench, CheckCircle2, AlertCircle } from "lucide-react"

interface ExhaustAnalysisProps {
  analysis: {
    classification: "stock" | "modified" | "unknown"
    confidence: number
    details: string[]
    modifications?: string[]
  }
}

export function ExhaustAnalysis({ analysis }: ExhaustAnalysisProps) {
  const isStock = analysis.classification === "stock"
  const isModified = analysis.classification === "modified"

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <Wrench className="h-5 w-5 text-primary" />
            Exhaust System
          </CardTitle>
          <Badge
            className={
              isStock
                ? "bg-emerald-500/10 text-emerald-500"
                : isModified
                  ? "bg-accent/10 text-accent"
                  : "bg-secondary text-secondary-foreground"
            }
          >
            {isStock && <CheckCircle2 className="mr-1 h-3 w-3" />}
            {isModified && <AlertCircle className="mr-1 h-3 w-3" />}
            {analysis.classification.charAt(0).toUpperCase() +
              analysis.classification.slice(1)}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center justify-between rounded-lg bg-secondary/50 p-3">
          <span className="text-muted-foreground">AI Confidence</span>
          <span className="font-semibold">{analysis.confidence}%</span>
        </div>

        <div>
          <h4 className="mb-2 text-sm font-medium text-muted-foreground">
            Analysis Details
          </h4>
          <ul className="space-y-1">
            {analysis.details.map((detail, index) => (
              <li key={index} className="flex items-start gap-2 text-sm">
                <span className="mt-1.5 h-1.5 w-1.5 rounded-full bg-primary" />
                {detail}
              </li>
            ))}
          </ul>
        </div>

        {analysis.modifications && analysis.modifications.length > 0 && (
          <div>
            <h4 className="mb-2 text-sm font-medium text-muted-foreground">
              Detected Modifications
            </h4>
            <div className="flex flex-wrap gap-2">
              {analysis.modifications.map((mod, index) => (
                <Badge key={index} variant="outline" className="text-accent border-accent/30">
                  {mod}
                </Badge>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
