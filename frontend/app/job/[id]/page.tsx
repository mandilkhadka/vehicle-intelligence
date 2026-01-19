import JobStatus from "@/components/JobStatus";
import Link from "next/link";
import { Car } from "lucide-react";

export default function JobPage({ params }: { params: { id: string } }) {
  return (
    <div className="min-h-screen bg-[#f8fafc]">
      <nav className="border-b border-slate-200 bg-white/80 backdrop-blur-xl">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between h-16">
            <div className="flex items-center gap-2">
              <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-600">
                <Car className="h-5 w-5 text-white" />
              </div>
              <Link href="/" className="text-xl font-semibold text-slate-900">
                Vehicle Intelligence Platform
              </Link>
            </div>
            <div className="flex items-center space-x-4">
              <Link
                href="/"
                className="text-sm font-medium text-slate-700 hover:text-blue-600 transition-colors px-3 py-2 rounded-md"
              >
                Home
              </Link>
            </div>
          </div>
        </div>
      </nav>

      <main className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
        <JobStatus jobId={params.id} />
      </main>
    </div>
  );
}
