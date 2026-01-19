import { Car, Gauge, Search, Wrench, Shield, Zap } from "lucide-react"

export function Features() {
  const features = [
    {
      icon: Car,
      title: "Vehicle Identification",
      description: "Automatically detect vehicle type (car/bike), brand, and model with confidence scoring.",
    },
    {
      icon: Gauge,
      title: "Odometer Detection",
      description: "Extract odometer readings using advanced OCR with multi-frame validation for accuracy.",
    },
    {
      icon: Search,
      title: "Damage Detection",
      description: "Identify scratches, dents, and rust with severity classification (low/high).",
    },
    {
      icon: Wrench,
      title: "Exhaust Analysis",
      description: "Classify exhaust systems as stock or modified with visual confidence scores.",
    },
    {
      icon: Shield,
      title: "Quality Assurance",
      description: "Confidence scoring on all outputs with flagging for low-quality results.",
    },
    {
      icon: Zap,
      title: "Fast Processing",
      description: "Complete end-to-end inspection in under 3 minutes with batch processing support.",
    },
  ]

  return (
    <section id="features" className="border-t border-slate-200 bg-white py-20 md:py-32">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-2xl text-center">
          <p className="text-sm font-medium uppercase tracking-wider text-primary">Features</p>
          <h2 className="mt-4 text-3xl font-bold text-foreground sm:text-4xl text-balance">
            Everything you need for vehicle inspection
          </h2>
          <p className="mt-4 text-muted-foreground text-pretty">
            Comprehensive AI-powered analysis covering all aspects of vehicle condition assessment.
          </p>
        </div>

        <div className="mt-16 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {features.map((feature, index) => (
            <div
              key={index}
              className="group relative overflow-hidden rounded-xl border border-slate-200 bg-white p-6 shadow-sm transition-all hover:border-blue-300 hover:shadow-md"
            >
              <div className="relative">
                <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-lg bg-blue-50 text-blue-600">
                  <feature.icon className="h-6 w-6" />
                </div>
                <h3 className="text-lg font-semibold text-foreground">{feature.title}</h3>
                <p className="mt-2 text-sm text-muted-foreground">{feature.description}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
