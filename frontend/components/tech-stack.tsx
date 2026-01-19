export function TechStack() {
  const technologies = [
    {
      name: "OpenCV",
      category: "Frame Extraction",
      description: "Extract frames from video at configurable intervals",
    },
    { name: "YOLOv8", category: "Object Detection", description: "Real-time object detection for damage and parts" },
    { name: "CLIP / ViT", category: "Model ID", description: "Vision transformers for vehicle identification" },
    { name: "PaddleOCR", category: "OCR", description: "State-of-the-art text recognition for odometers" },
    { name: "Custom CNN", category: "Classification", description: "Lightweight models for exhaust classification" },
    { name: "Gemini LLM", category: "Reasoning", description: "Generate structured reports and insights" },
  ]

  return (
    <section id="tech" className="border-t border-slate-200 bg-white py-20 md:py-32">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-2xl text-center">
          <p className="text-sm font-medium uppercase tracking-wider text-blue-600">Technology</p>
          <h2 className="mt-4 text-3xl font-bold text-foreground sm:text-4xl text-balance">
            Powered by cutting-edge AI
          </h2>
          <p className="mt-4 text-slate-600 text-pretty">
            Our platform combines multiple AI models working together for comprehensive vehicle analysis.
          </p>
        </div>

        <div className="mt-16 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {technologies.map((tech, index) => (
            <div
              key={index}
              className="group rounded-xl border border-slate-200 bg-white p-6 shadow-sm transition-all hover:border-blue-300 hover:shadow-md"
            >
              <div className="flex items-center gap-4">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-50 font-mono text-sm font-bold text-blue-600">
                  {tech.name.charAt(0)}
                </div>
                <div>
                  <h3 className="font-semibold text-slate-900">{tech.name}</h3>
                  <p className="text-xs font-medium text-blue-600">{tech.category}</p>
                </div>
              </div>
              <p className="mt-4 text-sm text-slate-600">{tech.description}</p>
            </div>
          ))}
        </div>

        {/* Architecture diagram placeholder */}
        <div className="mt-16 overflow-hidden rounded-xl border border-slate-200 bg-white p-8 shadow-sm">
          <div className="text-center">
            <p className="text-sm font-medium uppercase tracking-wider text-slate-600">System Architecture</p>
            <div className="mt-8 flex flex-wrap items-center justify-center gap-4">
              <div className="rounded-lg bg-blue-600 px-6 py-3 text-sm font-medium text-white shadow-sm">
                Next.js Frontend
              </div>
              <span className="text-slate-400">→</span>
              <div className="rounded-lg bg-blue-600 px-6 py-3 text-sm font-medium text-white shadow-sm">Node.js API</div>
              <span className="text-slate-400">→</span>
              <div className="rounded-lg bg-blue-600 px-6 py-3 text-sm font-medium text-white shadow-sm">
                Python ML Service
              </div>
              <span className="text-slate-400">→</span>
              <div className="rounded-lg bg-blue-600 px-6 py-3 text-sm font-medium text-white shadow-sm">
                Object Storage
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
