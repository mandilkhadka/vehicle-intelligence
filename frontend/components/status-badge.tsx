import { Badge } from "@/components/ui/badge";

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
