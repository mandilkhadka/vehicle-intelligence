import { AlertTriangle, ShieldCheck } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { AuditBadgeState } from "@/lib/inspection-audit";

export function StatusBadge({ status }: { status: string }) {
  switch (status) {
    case "completed":
      return (
        <Badge className="bg-emerald-500/10 text-emerald-500 hover:bg-emerald-500/20">
          Completed
        </Badge>
      );
    case "processing":
      return (
        <Badge className="bg-primary/10 text-primary hover:bg-primary/20">
          Processing
        </Badge>
      );
    case "pending":
      return <Badge variant="secondary">Pending</Badge>;
    case "failed":
      return (
        <Badge className="bg-destructive/10 text-destructive hover:bg-destructive/20">
          Failed
        </Badge>
      );
    default:
      return <Badge variant="secondary">{status}</Badge>;
  }
}

/**
 * Pipeline-audit verification badge shared by the history table and the
 * dashboard recent-inspections list.
 */
export function VerificationBadge({
  state,
  showDetail = false,
}: {
  state: AuditBadgeState;
  showDetail?: boolean;
}) {
  if (state.status === "verified") {
    return (
      <Badge className="gap-1 bg-emerald-500/10 text-emerald-500 hover:bg-emerald-500/20">
        <ShieldCheck className="h-3 w-3" />
        {state.label}
      </Badge>
    );
  }

  if (state.status === "review") {
    const badge = (
      <Badge variant="outline" className="gap-1 border-accent/40 text-accent">
        <AlertTriangle className="h-3 w-3" />
        {state.label}
      </Badge>
    );
    if (!showDetail) return badge;
    return (
      <div className="flex flex-col items-start gap-1">
        {badge}
        <span className="text-xs text-muted-foreground">{state.detail}</span>
      </div>
    );
  }

  return showDetail ? (
    <span className="text-sm text-muted-foreground">-</span>
  ) : null;
}
