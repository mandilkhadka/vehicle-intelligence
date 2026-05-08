import { use } from "react";
import JobStatus from "@/components/JobStatus";
import { Header } from "@/components/header";
import { Sidebar } from "@/components/sidebar";

export default function JobPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);

  return (
    <div className="min-h-screen bg-background">
      <Header />
      <div className="flex">
        <Sidebar />
        <main className="flex-1 overflow-auto">
          <div className="mx-auto max-w-3xl p-6">
            <div className="mb-6">
              <h1 className="text-2xl font-bold tracking-tight">Processing</h1>
              <p className="text-muted-foreground">
                Live status for job{" "}
                <span className="font-mono text-foreground">{id}</span>
              </p>
            </div>
            <JobStatus jobId={id} />
          </div>
        </main>
      </div>
    </div>
  );
}
