import { Navbar } from "@/components/navbar"
import { Hero } from "@/components/hero"
import { Stats } from "@/components/stats"
import { Features } from "@/components/features"
import { HowItWorks } from "@/components/how-it-works"
import { DetectionShowcase } from "@/components/detection-showcase"
import { TechStack } from "@/components/tech-stack"
import { ProcessingFlow } from "@/components/processing-flow"
import { FrameExtractionPipeline } from "@/components/frame-extraction-pipeline"
import { OutputPreview } from "@/components/output-preview"
import { CTA } from "@/components/cta"
import { Footer } from "@/components/footer"

export default function Home() {
  return (
    <div className="min-h-screen bg-background">
      <Navbar />
      <Hero />
      <Stats />
      <Features />
      <HowItWorks />
      <DetectionShowcase />
      <FrameExtractionPipeline />
      <ProcessingFlow />
      <OutputPreview />
      <TechStack />
      <CTA />
      <Footer />
    </div>
  )
}
