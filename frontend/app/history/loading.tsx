import { AppShell } from "@/components/app-shell"
import { PageHeader } from "@/components/page-header"
import { Card, CardContent, CardHeader } from "@/components/ui/card"

export default function Loading() {
  return (
    <AppShell>
      <div className="p-4 sm:p-6 lg:p-8">
        <PageHeader
          eyebrow="Records"
          title="History"
          description="Search, filter, and reopen completed vehicle inspections without leaving the operations console."
        />
        <Card>
          <CardHeader>
            <div className="h-5 w-40 animate-pulse rounded bg-secondary" />
            <div className="mt-2 h-4 w-56 animate-pulse rounded bg-secondary" />
          </CardHeader>
          <CardContent className="space-y-3">
            {[1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="flex items-center gap-4">
                <div className="h-10 w-14 animate-pulse rounded-lg bg-secondary" />
                <div className="h-4 flex-1 animate-pulse rounded bg-secondary" />
                <div className="h-4 w-24 animate-pulse rounded bg-secondary" />
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </AppShell>
  )
}
