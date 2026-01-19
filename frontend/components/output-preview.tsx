"use client"

import { useState } from "react"
import { Car, Gauge, AlertTriangle, Wind, CheckCircle2 } from "lucide-react"
import { cn } from "@/lib/utils"

export function OutputPreview() {
  const [activeSection, setActiveSection] = useState("vehicle")

  const sections = [
    { id: "vehicle", label: "Vehicle Info", icon: Car },
    { id: "odometer", label: "Odometer", icon: Gauge },
    { id: "damage", label: "Damage Report", icon: AlertTriangle },
    { id: "exhaust", label: "Exhaust", icon: Wind },
  ]

  const vehicleData = [
    { label: "Vehicle Type", value: "Car", confidence: "98%" },
    { label: "Brand", value: "BMW", confidence: "94%" },
    { label: "Model", value: "3 Series", confidence: "92%" },
    { label: "Year", value: "2023", confidence: "89%" },
    { label: "Color", value: "Alpine White", confidence: "96%" },
  ]

  const odometerData = [
    { label: "Reading", value: "45,892 km", confidence: "97%" },
    { label: "Display Type", value: "Digital", confidence: "99%" },
    { label: "Frames Analyzed", value: "12", confidence: "-" },
    { label: "Validation Status", value: "Verified", confidence: "97%" },
  ]

  const damageData = [
    { location: "Front Bumper", type: "Scratch", severity: "Low", confidence: "92%" },
    { location: "Driver Door", type: "Dent", severity: "High", confidence: "88%" },
    { location: "Rear Wheel Arch", type: "Rust", severity: "Low", confidence: "85%" },
  ]

  const exhaustData = [
    { label: "Classification", value: "Modified", confidence: "89%" },
    { label: "Pipe Configuration", value: "Dual Exit", confidence: "98%" },
    { label: "Type", value: "Aftermarket", confidence: "85%" },
    { label: "OEM Match", value: "No", confidence: "91%" },
  ]

  return (
    <section className="py-20 md:py-32">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-2xl text-center">
          <p className="text-sm font-medium uppercase tracking-wider text-primary">Inspection Results</p>
          <h2 className="mt-4 text-3xl font-bold text-foreground sm:text-4xl text-balance">
            Clear, actionable reports
          </h2>
          <p className="mt-4 text-muted-foreground text-pretty">
            Every inspection generates a comprehensive report that&apos;s easy to understand. All detections include
            confidence scores for quality assurance.
          </p>
        </div>

        {/* Section Tabs */}
        <div className="mt-12 flex flex-wrap justify-center gap-2">
          {sections.map((section) => (
            <button
              key={section.id}
              onClick={() => setActiveSection(section.id)}
              className={cn(
                "flex items-center gap-2 rounded-full px-5 py-2.5 text-sm font-medium transition-all",
                activeSection === section.id
                  ? "bg-primary text-primary-foreground"
                  : "bg-secondary text-muted-foreground hover:bg-secondary/80 hover:text-foreground",
              )}
            >
              <section.icon className="h-4 w-4" />
              {section.label}
            </button>
          ))}
        </div>

        {/* Tables */}
        <div className="mt-12 mx-auto max-w-4xl">
          {/* Vehicle Info Table */}
          {activeSection === "vehicle" && (
            <div className="rounded-2xl border border-border bg-card overflow-hidden">
              <div className="bg-secondary/50 px-6 py-4 border-b border-border">
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
                    <Car className="h-5 w-5 text-primary" />
                  </div>
                  <div>
                    <h3 className="font-semibold text-foreground">Vehicle Identification</h3>
                    <p className="text-sm text-muted-foreground">Detected using CLIP visual recognition</p>
                  </div>
                </div>
              </div>
              <div className="divide-y divide-border">
                {vehicleData.map((row, index) => (
                  <div key={index} className="flex items-center justify-between px-6 py-4">
                    <span className="text-muted-foreground">{row.label}</span>
                    <div className="flex items-center gap-4">
                      <span className="font-medium text-foreground">{row.value}</span>
                      <span className="text-xs text-primary bg-primary/10 px-2 py-1 rounded-full">
                        {row.confidence}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Odometer Table */}
          {activeSection === "odometer" && (
            <div className="rounded-2xl border border-border bg-card overflow-hidden">
              <div className="bg-secondary/50 px-6 py-4 border-b border-border">
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
                    <Gauge className="h-5 w-5 text-primary" />
                  </div>
                  <div>
                    <h3 className="font-semibold text-foreground">Odometer Reading</h3>
                    <p className="text-sm text-muted-foreground">Multi-frame averaged with PaddleOCR</p>
                  </div>
                </div>
              </div>
              <div className="p-6">
                <div className="text-center mb-6">
                  <p className="text-5xl font-bold text-foreground">45,892</p>
                  <p className="text-lg text-muted-foreground mt-1">kilometers</p>
                  <div className="flex items-center justify-center gap-2 mt-3">
                    <CheckCircle2 className="h-5 w-5 text-primary" />
                    <span className="text-sm text-primary font-medium">Verified across 12 frames</span>
                  </div>
                </div>
                <div className="divide-y divide-border border-t border-border">
                  {odometerData.map((row, index) => (
                    <div key={index} className="flex items-center justify-between py-3">
                      <span className="text-muted-foreground">{row.label}</span>
                      <div className="flex items-center gap-4">
                        <span className="font-medium text-foreground">{row.value}</span>
                        {row.confidence !== "-" && (
                          <span className="text-xs text-primary bg-primary/10 px-2 py-1 rounded-full">
                            {row.confidence}
                          </span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Damage Report Table */}
          {activeSection === "damage" && (
            <div className="rounded-2xl border border-border bg-card overflow-hidden">
              <div className="bg-secondary/50 px-6 py-4 border-b border-border">
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
                    <AlertTriangle className="h-5 w-5 text-primary" />
                  </div>
                  <div>
                    <h3 className="font-semibold text-foreground">Damage Report</h3>
                    <p className="text-sm text-muted-foreground">Detected using YOLOv8 + Custom CNN</p>
                  </div>
                </div>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-border bg-secondary/30">
                      <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                        Location
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                        Type
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                        Severity
                      </th>
                      <th className="px-6 py-3 text-right text-xs font-medium uppercase tracking-wider text-muted-foreground">
                        Confidence
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {damageData.map((row, index) => (
                      <tr key={index}>
                        <td className="px-6 py-4 whitespace-nowrap text-foreground font-medium">{row.location}</td>
                        <td className="px-6 py-4 whitespace-nowrap text-muted-foreground">{row.type}</td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          <span
                            className={cn(
                              "inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium",
                              row.severity === "High"
                                ? "bg-destructive/10 text-destructive"
                                : row.severity === "Medium"
                                  ? "bg-chart-4/10 text-chart-4"
                                  : "bg-primary/10 text-primary",
                            )}
                          >
                            {row.severity}
                          </span>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-right">
                          <span className="text-xs text-primary bg-primary/10 px-2 py-1 rounded-full">
                            {row.confidence}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="px-6 py-4 bg-secondary/30 border-t border-border">
                <p className="text-sm text-muted-foreground">
                  <span className="font-medium text-foreground">Summary:</span> 3 issues detected - 1 high severity, 2
                  low severity
                </p>
              </div>
            </div>
          )}

          {/* Exhaust Table */}
          {activeSection === "exhaust" && (
            <div className="rounded-2xl border border-border bg-card overflow-hidden">
              <div className="bg-secondary/50 px-6 py-4 border-b border-border">
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
                    <Wind className="h-5 w-5 text-primary" />
                  </div>
                  <div>
                    <h3 className="font-semibold text-foreground">Exhaust Analysis</h3>
                    <p className="text-sm text-muted-foreground">Binary CNN classification model</p>
                  </div>
                </div>
              </div>
              <div className="p-6">
                <div className="text-center mb-6 py-4 rounded-xl bg-chart-4/10 border border-chart-4/20">
                  <p className="text-sm text-chart-4 font-medium uppercase tracking-wider">Status</p>
                  <p className="text-3xl font-bold text-chart-4 mt-1">Modified Exhaust</p>
                  <p className="text-sm text-muted-foreground mt-2">Aftermarket dual-exit configuration detected</p>
                </div>
                <div className="divide-y divide-border">
                  {exhaustData.map((row, index) => (
                    <div key={index} className="flex items-center justify-between py-3">
                      <span className="text-muted-foreground">{row.label}</span>
                      <div className="flex items-center gap-4">
                        <span className="font-medium text-foreground">{row.value}</span>
                        <span className="text-xs text-primary bg-primary/10 px-2 py-1 rounded-full">
                          {row.confidence}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Features List */}
        <div className="mt-12 mx-auto max-w-2xl">
          <ul className="grid gap-4 sm:grid-cols-2">
            {[
              "Vehicle identification with brand, model, and year",
              "Validated odometer reading with multi-frame averaging",
              "Detailed damage report with location and severity",
              "Exhaust classification with modification detection",
            ].map((item, index) => (
              <li key={index} className="flex items-start gap-3 rounded-lg bg-secondary/50 p-4">
                <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary/20 text-xs text-primary">
                  ✓
                </span>
                <span className="text-sm text-muted-foreground">{item}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  )
}
