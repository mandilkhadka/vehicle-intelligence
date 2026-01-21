"use client"

import { useState } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Sparkles, Eye, Gauge, PaintBucket, Wrench } from "lucide-react"

const detectionOptions = [
  {
    id: "damage",
    label: "Damage Detection",
    description: "Scratches, dents, and body damage",
    icon: Eye,
    defaultEnabled: true,
  },
  {
    id: "odometer",
    label: "Odometer Reading",
    description: "Extract mileage from dashboard",
    icon: Gauge,
    defaultEnabled: true,
  },
  {
    id: "paint",
    label: "Paint Analysis",
    description: "Paint chips, fading, and rust",
    icon: PaintBucket,
    defaultEnabled: true,
  },
  {
    id: "exhaust",
    label: "Exhaust Classification",
    description: "Stock vs modified exhaust",
    icon: Wrench,
    defaultEnabled: false,
  },
]

export function InspectionOptions() {
  const [options, setOptions] = useState<Record<string, boolean>>(
    detectionOptions.reduce(
      (acc, opt) => ({ ...acc, [opt.id]: opt.defaultEnabled }),
      {}
    )
  )

  const toggleOption = (id: string) => {
    setOptions((prev) => ({ ...prev, [id]: !prev[id] }))
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Sparkles className="h-5 w-5 text-primary" />
          <CardTitle>AI Detection Options</CardTitle>
        </div>
        <CardDescription>
          Configure what the AI should analyze in your video
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="space-y-4">
          {detectionOptions.map((option) => {
            const Icon = option.icon
            return (
              <div
                key={option.id}
                className="flex items-center justify-between rounded-lg border border-border bg-secondary/30 p-4"
              >
                <div className="flex items-center gap-3">
                  <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10">
                    <Icon className="h-4 w-4 text-primary" />
                  </div>
                  <div>
                    <Label htmlFor={option.id} className="cursor-pointer font-medium">
                      {option.label}
                    </Label>
                    <p className="text-sm text-muted-foreground">
                      {option.description}
                    </p>
                  </div>
                </div>
                <Switch
                  id={option.id}
                  checked={options[option.id]}
                  onCheckedChange={() => toggleOption(option.id)}
                />
              </div>
            )
          })}
        </div>

        <div className="space-y-3 border-t border-border pt-4">
          <Label>AI Model</Label>
          <Select defaultValue="advanced">
            <SelectTrigger>
              <SelectValue placeholder="Select model" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="fast">Fast (Basic analysis)</SelectItem>
              <SelectItem value="standard">Standard (Balanced)</SelectItem>
              <SelectItem value="advanced">Advanced (Most accurate)</SelectItem>
            </SelectContent>
          </Select>
          <p className="text-xs text-muted-foreground">
            Advanced model provides the most detailed analysis but takes longer
          </p>
        </div>
      </CardContent>
    </Card>
  )
}
