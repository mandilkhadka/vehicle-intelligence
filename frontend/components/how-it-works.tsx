import { Upload, Clapperboard, Cpu, FileJson } from "lucide-react"

export function HowItWorks() {
  const steps = [
    {
      icon: Upload,
      step: "01",
      title: "Upload Video",
      description: "Upload your 360-degree walk-around video in MP4 format. Capture the entire vehicle exterior.",
    },
    {
      icon: Clapperboard,
      step: "02",
      title: "Frame Extraction",
      description: "Our system extracts frames at fixed intervals, creating a comprehensive visual dataset.",
    },
    {
      icon: Cpu,
      step: "03",
      title: "AI Analysis",
      description: "Multiple AI models analyze frames for vehicle ID, odometer reading, damage, and modifications.",
    },
    {
      icon: FileJson,
      step: "04",
      title: "Structured Output",
      description: "Receive a complete inspection report in JSON format with confidence scores for each detection.",
    },
  ]

  return (
    <section id="how-it-works" className="py-20 md:py-32 bg-white">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-2xl text-center">
          <p className="text-sm font-medium uppercase tracking-wider text-blue-600">How It Works</p>
          <h2 className="mt-4 text-3xl font-bold text-foreground sm:text-4xl text-balance">
            From video to inspection in four steps
          </h2>
          <p className="mt-4 text-slate-600 text-pretty">
            Our streamlined process transforms raw video footage into actionable inspection data with minimal effort.
          </p>
        </div>

        <div className="relative mt-16">
          {/* Connection line */}
          <div className="absolute left-1/2 top-0 hidden h-full w-px -translate-x-1/2 bg-slate-200 md:block" />

          <div className="grid gap-8 md:grid-cols-2 lg:grid-cols-4">
            {steps.map((step, index) => (
              <div
                key={index}
                className="group relative rounded-xl border border-slate-200 bg-white p-6 shadow-sm transition-all hover:border-blue-300 hover:shadow-md"
              >
                <div className="mb-4 flex items-center justify-between">
                  <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-blue-50 text-blue-600">
                    <step.icon className="h-6 w-6" />
                  </div>
                  <span className="font-mono text-sm font-bold text-slate-400">{step.step}</span>
                </div>
                <h3 className="text-lg font-semibold text-foreground">{step.title}</h3>
                <p className="mt-2 text-sm text-slate-600">{step.description}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}
