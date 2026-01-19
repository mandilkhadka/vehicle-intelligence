import { Car } from "lucide-react"

export function Footer() {
  return (
    <footer className="border-t border-slate-200 bg-white py-12">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="flex flex-col items-center justify-between gap-6 md:flex-row">
          <div className="flex items-center gap-2">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-600">
              <Car className="h-5 w-5 text-white" />
            </div>
            <span className="text-xl font-semibold text-slate-900">VIP</span>
          </div>
          <p className="text-sm text-slate-600">© 2026 Vehicle Intelligence Platform. All rights reserved.</p>
          <div className="flex items-center gap-6">
            <a href="#" className="text-sm text-slate-600 transition-colors hover:text-blue-600">
              Privacy
            </a>
            <a href="#" className="text-sm text-slate-600 transition-colors hover:text-blue-600">
              Terms
            </a>
            <a href="#" className="text-sm text-slate-600 transition-colors hover:text-blue-600">
              Documentation
            </a>
          </div>
        </div>
      </div>
    </footer>
  )
}
