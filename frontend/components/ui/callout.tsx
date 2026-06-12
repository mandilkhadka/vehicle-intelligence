import * as React from "react";
import { AlertTriangle, Info, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";

type CalloutVariant = "warning" | "destructive" | "info";

const VARIANT_CLASSES: Record<CalloutVariant, string> = {
  warning:
    "border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-900/40 dark:bg-amber-950/30 dark:text-amber-200",
  destructive: "border-destructive/30 bg-destructive/5 text-destructive",
  info: "border-border bg-secondary/40 text-muted-foreground",
};

const VARIANT_ICONS: Record<CalloutVariant, React.ComponentType<{ className?: string }>> = {
  warning: AlertTriangle,
  destructive: XCircle,
  info: Info,
};

/**
 * Canonical inline alert box. Use instead of hand-rolled amber/destructive
 * bordered divs so warnings read identically across pages.
 */
export function Callout({
  variant = "info",
  icon = true,
  className,
  children,
}: {
  variant?: CalloutVariant;
  /** Set false to suppress the leading icon (e.g. for dense layouts). */
  icon?: boolean;
  className?: string;
  children: React.ReactNode;
}) {
  const IconComponent = VARIANT_ICONS[variant];
  return (
    <div
      role={variant === "destructive" ? "alert" : "status"}
      className={cn(
        "flex items-start gap-2 rounded-md border p-3 text-sm",
        VARIANT_CLASSES[variant],
        className,
      )}
    >
      {icon && <IconComponent className="mt-0.5 h-4 w-4 shrink-0" />}
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}
