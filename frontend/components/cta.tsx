import { Button } from "@/components/ui/button"
import { ArrowRight } from "lucide-react"
import Link from "next/link"

export function CTA() {
  return (
    <section className="border-t border-slate-200 bg-slate-50 py-20 md:py-32">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="relative overflow-hidden rounded-xl border border-slate-200 bg-white p-8 md:p-16 shadow-lg">

          <div className="relative mx-auto max-w-2xl text-center">
            <h2 className="text-3xl font-bold text-foreground sm:text-4xl text-balance">
              Ready to transform your vehicle inspections?
            </h2>
            <p className="mt-4 text-lg text-muted-foreground text-pretty">
              Join vehicle inspectors and dealerships already using VIP to streamline their inspection workflow.
            </p>
            <div className="mt-8 flex flex-col items-center justify-center gap-4 sm:flex-row">
              <Button size="lg" className="gap-2" asChild>
                <Link href="/upload">
                  Get Started Free
                  <ArrowRight className="h-4 w-4" />
                </Link>
              </Button>
              <Button size="lg" variant="outline">
                Contact Sales
              </Button>
            </div>
            <p className="mt-6 text-sm text-muted-foreground">No credit card required • Free tier available</p>
          </div>
        </div>
      </div>
    </section>
  )
}
