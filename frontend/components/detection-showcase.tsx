"use client"

import { useState } from "react"
import Image from "next/image"
import { cn } from "@/lib/utils"

export function DetectionShowcase() {
  const [activeTab, setActiveTab] = useState("damage")

  const tabs = [
    { id: "damage", label: "Damage Detection" },
    { id: "odometer", label: "Odometer Reading" },
    { id: "exhaust", label: "Exhaust Analysis" },
  ]

  const content = {
    damage: {
      image: "/car-exterior-showing-detected-scratch-and-dent-wit.jpg",
      title: "Intelligent Damage Detection",
      description:
        "Our AI models detect and classify damage including scratches, dents, and rust. Each detection includes severity classification and precise location mapping.",
      detections: [
        { type: "Scratch", severity: "Low", confidence: "92%", location: "Front bumper" },
        { type: "Dent", severity: "High", confidence: "88%", location: "Driver door" },
        { type: "Rust", severity: "Low", confidence: "95%", location: "Wheel arch" },
      ],
    },
    odometer: {
      image: "/car-dashboard-speedometer-and-odometer-display-clo.jpg",
      title: "Precision OCR for Odometer",
      description:
        "Multi-frame averaging ensures accurate odometer readings. Dashboard regions are automatically detected and processed through advanced OCR pipelines.",
      detections: [
        { type: "Primary Reading", severity: "45,892 km", confidence: "96%", location: "Digital display" },
        { type: "Validation", severity: "45,891 km", confidence: "94%", location: "Frame 24" },
        { type: "Final Output", severity: "45,892 km", confidence: "97%", location: "Averaged" },
      ],
    },
    exhaust: {
      image: "/car-rear-exhaust-pipe-closeup-for-modification-det.jpg",
      title: "Exhaust Modification Detection",
      description:
        "Lightweight CNN models classify exhaust systems as stock or modified. Visual analysis compares against known OEM configurations.",
      detections: [
        { type: "Classification", severity: "Modified", confidence: "89%", location: "Rear" },
        { type: "Pipe Count", severity: "Dual", confidence: "98%", location: "Visual" },
        { type: "Type", severity: "Aftermarket", confidence: "85%", location: "Pattern match" },
      ],
    },
  }

  const activeContent = content[activeTab as keyof typeof content]

  return (
    <section id="detection" className="py-20 md:py-32 bg-slate-50">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-2xl text-center">
          <p className="text-sm font-medium uppercase tracking-wider text-blue-600">Detection Capabilities</p>
          <h2 className="mt-4 text-3xl font-bold text-foreground sm:text-4xl text-balance">See our AI in action</h2>
          <p className="mt-4 text-slate-600 text-pretty">
            Explore how VIP detects and analyzes different aspects of vehicle condition.
          </p>
        </div>

        {/* Tabs */}
        <div className="mt-12 flex flex-wrap justify-center gap-2">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={cn(
                "rounded-full px-6 py-2 text-sm font-medium transition-all",
                activeTab === tab.id
                  ? "bg-blue-600 text-white shadow-sm"
                  : "bg-white text-slate-600 hover:bg-slate-50 border border-slate-200",
              )}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="mt-12 grid gap-8 lg:grid-cols-2 lg:items-center">
          <div className="relative aspect-video overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
            <Image
              src={activeContent.image || "/placeholder.svg"}
              alt={activeContent.title}
              fill
              className="object-cover"
              unoptimized
            />
          </div>
          <div>
            <h3 className="text-2xl font-bold text-slate-900">{activeContent.title}</h3>
            <p className="mt-4 text-slate-600">{activeContent.description}</p>

            <div className="mt-8 space-y-4">
              {activeContent.detections.map((detection, index) => (
                <div
                  key={index}
                  className="flex items-center justify-between rounded-lg border border-slate-200 bg-white p-4 shadow-sm hover:shadow-md transition-shadow"
                >
                  <div>
                    <p className="font-medium text-slate-900">{detection.type}</p>
                    <p className="text-sm text-slate-500">{detection.location}</p>
                  </div>
                  <div className="text-right">
                    <p className="font-mono text-sm font-semibold text-slate-900">{detection.severity}</p>
                    <p className="text-xs text-blue-600 font-medium">{detection.confidence} confidence</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
