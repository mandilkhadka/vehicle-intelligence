import { Button } from "@/components/ui/button"
import { ArrowRight, Play, Upload } from "lucide-react"
import Link from "next/link"

export function Hero() {
  return (
    <section className="relative overflow-hidden pt-32 pb-20 md:pt-40 md:pb-32">
      {/* Subtle background */}
      <div className="absolute inset-0 -z-10">
        {/* Very subtle grid overlay */}
        <div className="absolute inset-0 bg-[linear-gradient(to_right,rgba(148,163,184,0.03)_1px,transparent_1px),linear-gradient(to_bottom,rgba(148,163,184,0.03)_1px,transparent_1px)] bg-[size:4rem_4rem]" />
      </div>

      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-4xl text-center">
          <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-4 py-1.5 text-sm font-medium text-slate-700 shadow-sm">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-blue-500 opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-blue-500" />
            </span>
            AI-Powered Vehicle Inspection
          </div>

          <h1 className="text-4xl font-bold tracking-tight text-slate-900 sm:text-5xl md:text-6xl lg:text-7xl text-balance">
            Transform video into <span className="text-blue-600">structured inspection data</span>
          </h1>

          <p className="mx-auto mt-6 max-w-2xl text-lg text-slate-600 md:text-xl text-pretty">
            Upload a 360° walk-around video and let our AI extract vehicle model, odometer reading, damage detection,
            and more — all in under 3 minutes.
          </p>

          <div className="mt-10 flex flex-col items-center justify-center gap-4 sm:flex-row">
            <Button size="lg" className="gap-2" asChild>
              <Link href="/upload">
                <Upload className="h-4 w-4" />
                Upload Video
                <ArrowRight className="h-4 w-4" />
              </Link>
            </Button>
            <Button size="lg" variant="outline" className="gap-2 bg-transparent">
              <Play className="h-4 w-4" />
              Watch Demo
            </Button>
          </div>
        </div>

        {/* Hero visual */}
        <div className="relative mx-auto mt-16 max-w-5xl">
          <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-xl">
            <div className="flex items-center gap-2 border-b border-slate-200 bg-slate-50 px-4 py-3">
              <div className="h-3 w-3 rounded-full bg-red-500" />
              <div className="h-3 w-3 rounded-full bg-yellow-500" />
              <div className="h-3 w-3 rounded-full bg-green-500" />
              <span className="ml-4 text-sm font-medium text-slate-600">VIP Inspector Dashboard</span>
            </div>
            <div className="p-6 bg-white">
              <div className="grid gap-6 md:grid-cols-2">
                <div className="aspect-video overflow-hidden rounded-lg bg-slate-100">
                  <video
                    autoPlay
                    loop
                    muted
                    playsInline
                    className="h-full w-full object-cover"
                    poster="/car-inspection-video-thumbnail.jpg"
                  >
                    <source
                      src="https://videos.pexels.com/video-files/3764984/3764984-uhd_2560_1440_25fps.mp4"
                      type="video/mp4"
                    />
                    Your browser does not support the video tag.
                  </video>
                </div>
                {/* End video change */}
                <div className="space-y-4">
                  <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
                    <p className="text-xs uppercase tracking-wider text-slate-500 font-medium">Vehicle Identified</p>
                    <p className="mt-1 text-lg font-semibold text-slate-900">2023 BMW 3 Series</p>
                    <div className="mt-2 flex items-center gap-2">
                      <span className="rounded-full bg-blue-100 px-2 py-0.5 text-xs text-blue-700 font-medium">
                        94% confidence
                      </span>
                    </div>
                  </div>
                  <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
                    <p className="text-xs uppercase tracking-wider text-slate-500 font-medium">Odometer Reading</p>
                    <p className="mt-1 font-mono text-2xl font-bold text-slate-900">45,892 km</p>
                  </div>
                  <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
                    <p className="text-xs uppercase tracking-wider text-slate-500 font-medium">Damage Detected</p>
                    <div className="mt-2 flex flex-wrap gap-2">
                      <span className="rounded-full bg-yellow-100 px-2 py-0.5 text-xs text-yellow-700 font-medium">2 scratches</span>
                      <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs text-red-700 font-medium">
                        1 dent
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
