import { use } from "react";
import JobStatus from "@/components/JobStatus";
import { AppShell } from "@/components/app-shell";
import { PageHeader } from "@/components/page-header";

export default function JobPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);

  return (
    <AppShell>
      <div className="mx-auto max-w-3xl p-4 sm:p-6 lg:p-8">
        <PageHeader
          eyebrow="Pipeline"
          title="Processing"
          description={
            <>
              Live status for job <span className="font-mono text-foreground">{id}</span>
            </>
          }
        />
        <JobStatus jobId={id} />
      </div>
    </AppShell>
  );
}
