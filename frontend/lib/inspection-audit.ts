import type { InspectionRecord, PipelineAudit } from "@/lib/api";
import { safeParseJsonOrValue } from "@/lib/utils/safe-json";

type ReportWithAudit = Record<string, unknown> & {
  pipeline_audit?: PipelineAudit;
};

export type AuditBadgeState = {
  audit?: PipelineAudit;
  label: string;
  detail: string;
  status: "verified" | "review" | "unknown";
};

export function getInspectionPipelineAudit(
  inspection: Pick<InspectionRecord, "inspection_report">,
): PipelineAudit | undefined {
  const report = safeParseJsonOrValue<ReportWithAudit>(
    inspection.inspection_report as string | ReportWithAudit | null | undefined,
    {},
  );
  const audit = report.pipeline_audit;

  if (!audit || typeof audit !== "object") return undefined;
  return audit as PipelineAudit;
}

export function getAuditBadgeState(
  audit: PipelineAudit | undefined,
): AuditBadgeState {
  if (!audit) {
    return {
      label: "Not audited",
      detail: "No pipeline audit attached",
      status: "unknown",
    };
  }

  if (audit.passed || audit.status === "complete") {
    return {
      audit,
      label: "Verified",
      detail: "All checks passed",
      status: "verified",
    };
  }

  const missing = Array.isArray(audit.missing) ? audit.missing.length : 0;
  return {
    audit,
    label: "Needs review",
    detail:
      missing > 0 ? `${missing} check${missing === 1 ? "" : "s"}` : "Incomplete",
    status: "review",
  };
}
