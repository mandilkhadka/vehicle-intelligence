"use client"

import { ArrowRight, Video, ImageIcon, Brain, Database, FileText, Scan } from "lucide-react"

export function ProcessingFlow() {
  const stages = [
    {
      icon: Video,
      title: "Video Input",
      subtitle: "MP4 Upload",
      items: ["360° walk-around", "Dashboard footage", "Any resolution"],
      color: "from-blue-500/20 to-blue-600/20",
      borderColor: "border-blue-500/30",
    },
    {
      icon: ImageIcon,
      title: "Frame Extraction",
      subtitle: "OpenCV",
      items: ["Fixed interval sampling", "Keyframe detection", "Quality filtering"],
      color: "from-cyan-500/20 to-cyan-600/20",
      borderColor: "border-cyan-500/30",
    },
    {
      icon: Scan,
      title: "Region Detection",
      subtitle: "YOLO + CLIP",
      items: ["Dashboard ROI", "Body panels", "Exhaust area"],
      color: "from-teal-500/20 to-teal-600/20",
      borderColor: "border-teal-500/30",
    },
    {
      icon: Brain,
      title: "AI Analysis",
      subtitle: "Multi-Model",
      items: ["Damage detection", "OCR processing", "Classification"],
      color: "from-emerald-500/20 to-emerald-600/20",
      borderColor: "border-emerald-500/30",
    },
    {
      icon: Database,
      title: "Aggregation",
      subtitle: "Consensus",
      items: ["Multi-frame averaging", "Confidence scoring", "Deduplication"],
      color: "from-green-500/20 to-green-600/20",
      borderColor: "border-green-500/30",
    },
    {
      icon: FileText,
      title: "Report",
      subtitle: "Easy to Read",
      items: ["Clear tables", "Confidence scores", "Actionable insights"],
      color: "from-lime-500/20 to-lime-600/20",
      borderColor: "border-lime-500/30",
    },
  ]

  return (
    <section className="py-20 md:py-32">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-2xl text-center">
          <p className="text-sm font-medium uppercase tracking-wider text-primary">Complete Processing Flow</p>
          <h2 className="mt-4 text-3xl font-bold text-foreground sm:text-4xl text-balance">
            End-to-end inspection pipeline
          </h2>
          <p className="mt-4 text-muted-foreground text-pretty">
            Follow the data journey from raw video to structured inspection report through our multi-stage processing
            architecture.
          </p>
        </div>

        {/* Flow Diagram */}
        <div className="mt-16 relative">
          {/* Connection line for desktop */}
          <div className="hidden lg:block absolute top-1/2 left-0 right-0 h-0.5 bg-gradient-to-r from-blue-500/30 via-emerald-500/30 to-lime-500/30 -translate-y-1/2" />

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-6">
            {stages.map((stage, index) => (
              <div key={index} className="relative">
                <div
                  className={`rounded-xl border ${stage.borderColor} bg-gradient-to-br ${stage.color} p-4 h-full backdrop-blur-sm`}
                >
                  <div className="flex items-center gap-2 mb-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-background/50">
                      <stage.icon className="h-5 w-5 text-primary" />
                    </div>
                    <div>
                      <p className="text-xs text-muted-foreground">{stage.subtitle}</p>
                      <h3 className="text-sm font-semibold text-foreground">{stage.title}</h3>
                    </div>
                  </div>
                  <ul className="space-y-1">
                    {stage.items.map((item, itemIndex) => (
                      <li key={itemIndex} className="text-xs text-muted-foreground flex items-center gap-1">
                        <span className="h-1 w-1 rounded-full bg-primary/50" />
                        {item}
                      </li>
                    ))}
                  </ul>
                </div>

                {/* Arrow between stages */}
                {index < stages.length - 1 && (
                  <div className="hidden lg:flex absolute -right-2 top-1/2 -translate-y-1/2 z-10">
                    <ArrowRight className="h-4 w-4 text-primary/50" />
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Summary Cards instead of code */}
        <div className="mt-16 grid gap-6 md:grid-cols-3">
          <div className="rounded-xl border border-border bg-card p-6">
            <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-blue-500/10 mb-4">
              <ImageIcon className="h-6 w-6 text-blue-500" />
            </div>
            <h3 className="font-semibold text-foreground mb-2">Smart Frame Selection</h3>
            <p className="text-sm text-muted-foreground">
              Frames are extracted at optimal intervals with built-in blur detection to ensure only high-quality images
              are processed by our AI models.
            </p>
          </div>
          <div className="rounded-xl border border-border bg-card p-6">
            <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-emerald-500/10 mb-4">
              <Brain className="h-6 w-6 text-emerald-500" />
            </div>
            <h3 className="font-semibold text-foreground mb-2">Multi-Model Analysis</h3>
            <p className="text-sm text-muted-foreground">
              Each frame passes through specialized AI models for vehicle identification, damage detection, odometer
              reading, and exhaust classification.
            </p>
          </div>
          <div className="rounded-xl border border-border bg-card p-6">
            <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-lime-500/10 mb-4">
              <Database className="h-6 w-6 text-lime-500" />
            </div>
            <h3 className="font-semibold text-foreground mb-2">Consensus Aggregation</h3>
            <p className="text-sm text-muted-foreground">
              Results from multiple frames are aggregated using consensus algorithms to produce accurate, reliable final
              readings with confidence scores.
            </p>
          </div>
        </div>
      </div>
    </section>
  )
}
