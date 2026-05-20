"use client";

import {
  Document,
  Image as PdfImage,
  Page,
  StyleSheet,
  Text,
  View,
} from "@react-pdf/renderer";

// Cost / damage shapes match what DamageInfo consumes. Kept local on purpose:
// the PDF is a snapshot of what the screen showed at download time and should
// not chase shared schema drift.

interface EstimatedCost {
  low: number;
  high: number;
  midpoint: number;
  currency: string;
}

interface DamageLocation {
  type?: string;
  part?: string;
  part_label?: string;
  confidence?: number;
  severity?: string;
  snapshot?: string | null;
  bbox?: number[];
  rationale?: string | null;
  estimated_cost?: EstimatedCost | null;
}

interface TotalCost extends EstimatedCost {
  has_unknowns?: boolean;
  counted_locations?: number;
  unknown_locations?: number;
}

export interface InspectionPdfData {
  inspectionId: string;
  generatedAt: string;
  backendBaseUrl: string;
  vehicle?: {
    type?: string;
    brand?: string;
    model?: string;
    year?: string | number;
    variant?: string;
    color?: string;
    confidence?: number;
    vin?: string;
    registration?: string;
  };
  odometer?: {
    value?: number | null;
    confidence?: number | null;
    source?: string;
  };
  exhaust?: {
    type?: string;
    confidence?: number;
  };
  damage?: {
    severity?: string;
    locations?: DamageLocation[];
    total_estimated_repair_cost?: TotalCost | null;
    counts?: Record<string, number>;
  };
}

const styles = StyleSheet.create({
  page: {
    padding: 36,
    fontFamily: "Helvetica",
    fontSize: 10,
    color: "#0f172a",
  },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "flex-start",
    borderBottomWidth: 2,
    borderBottomColor: "#0f172a",
    paddingBottom: 10,
    marginBottom: 16,
  },
  brand: {
    fontSize: 18,
    fontWeight: "bold",
  },
  subtitle: {
    fontSize: 9,
    color: "#475569",
    marginTop: 2,
  },
  meta: {
    fontSize: 9,
    textAlign: "right",
    color: "#475569",
  },
  section: {
    marginBottom: 14,
  },
  sectionTitle: {
    fontSize: 12,
    fontWeight: "bold",
    marginBottom: 6,
    color: "#0f172a",
    textTransform: "uppercase",
    letterSpacing: 0.5,
  },
  rowWrap: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 6,
  },
  card: {
    width: "32%",
    borderWidth: 1,
    borderColor: "#e2e8f0",
    borderRadius: 4,
    padding: 6,
    marginBottom: 6,
    marginRight: "1.5%",
  },
  label: {
    fontSize: 8,
    color: "#64748b",
    textTransform: "uppercase",
  },
  value: {
    fontSize: 11,
    fontWeight: "bold",
    marginTop: 2,
  },
  badgeRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    marginBottom: 4,
  },
  badge: {
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 3,
    fontSize: 8,
    fontWeight: "bold",
    textTransform: "uppercase",
    color: "#fff",
  },
  severityHigh: { backgroundColor: "#dc2626" },
  severityMedium: { backgroundColor: "#d97706" },
  severityLow: { backgroundColor: "#16a34a" },
  table: {
    borderWidth: 1,
    borderColor: "#e2e8f0",
    borderRadius: 4,
  },
  tableHeader: {
    flexDirection: "row",
    backgroundColor: "#f1f5f9",
    paddingVertical: 5,
    paddingHorizontal: 6,
    borderBottomWidth: 1,
    borderBottomColor: "#e2e8f0",
  },
  tableRow: {
    flexDirection: "row",
    paddingVertical: 5,
    paddingHorizontal: 6,
    borderBottomWidth: 1,
    borderBottomColor: "#f1f5f9",
  },
  th: {
    fontSize: 9,
    fontWeight: "bold",
    color: "#475569",
  },
  td: {
    fontSize: 9,
  },
  colPart: { flex: 2.4 },
  colCount: { flex: 0.8, textAlign: "right" },
  colSeverity: { flex: 1, textAlign: "center" },
  colTypes: { flex: 2 },
  colCost: { flex: 1.5, textAlign: "right" },
  snapshotRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 6,
    marginTop: 8,
  },
  snapshot: {
    width: "31.5%",
    marginRight: "1.5%",
    marginBottom: 8,
    borderWidth: 1,
    borderColor: "#e2e8f0",
    borderRadius: 4,
    padding: 4,
  },
  snapshotImage: {
    width: "100%",
    height: 80,
    objectFit: "cover",
    borderRadius: 2,
  },
  snapshotMeta: {
    fontSize: 8,
    marginTop: 3,
    color: "#0f172a",
    fontWeight: "bold",
  },
  snapshotSub: {
    fontSize: 7,
    color: "#64748b",
    marginTop: 1,
  },
  rationale: {
    fontSize: 7,
    color: "#475569",
    marginTop: 2,
    fontStyle: "italic",
  },
  footer: {
    position: "absolute",
    bottom: 20,
    left: 36,
    right: 36,
    flexDirection: "row",
    justifyContent: "space-between",
    fontSize: 8,
    color: "#94a3b8",
    borderTopWidth: 1,
    borderTopColor: "#e2e8f0",
    paddingTop: 6,
  },
  empty: {
    color: "#64748b",
    fontStyle: "italic",
  },
});

const SEVERITY_RANK: Record<string, number> = { low: 1, medium: 2, high: 3 };

function severityStyle(sev?: string) {
  switch ((sev || "low").toLowerCase()) {
    case "high":
      return styles.severityHigh;
    case "medium":
      return styles.severityMedium;
    default:
      return styles.severityLow;
  }
}

function formatCurrency(amount: number, currency: string): string {
  try {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency,
      maximumFractionDigits: 0,
    }).format(amount);
  } catch {
    return `${currency} ${Math.round(amount)}`;
  }
}

function formatRange(cost: EstimatedCost): string {
  if (cost.low === cost.high) return formatCurrency(cost.low, cost.currency);
  return `${formatCurrency(cost.low, cost.currency)} – ${formatCurrency(cost.high, cost.currency)}`;
}

function snapshotUrl(backendBaseUrl: string, snapshot: string): string {
  const path = snapshot.startsWith("uploads/") ? snapshot : `uploads/${snapshot}`;
  return `${backendBaseUrl}/${path}`;
}

interface PartGroup {
  part: string;
  partLabel: string;
  locations: DamageLocation[];
  totalLow: number;
  totalHigh: number;
  currency: string;
  maxSeverity: string;
  hasCost: boolean;
  types: Set<string>;
}

function groupByPart(locations: DamageLocation[]): PartGroup[] {
  const map = new Map<string, PartGroup>();
  for (const loc of locations) {
    const part = loc.part || "unknown";
    const partLabel = loc.part_label || part.replace(/_/g, " ");
    let group = map.get(part);
    if (!group) {
      group = {
        part,
        partLabel,
        locations: [],
        totalLow: 0,
        totalHigh: 0,
        currency: loc.estimated_cost?.currency || "USD",
        maxSeverity: "low",
        hasCost: false,
        types: new Set<string>(),
      };
      map.set(part, group);
    }
    group.locations.push(loc);
    if (loc.type) group.types.add(loc.type);
    if (loc.estimated_cost) {
      group.totalLow += loc.estimated_cost.low;
      group.totalHigh += loc.estimated_cost.high;
      group.hasCost = true;
      group.currency = loc.estimated_cost.currency;
    }
    const sev = (loc.severity || "low").toLowerCase();
    if ((SEVERITY_RANK[sev] ?? 0) > (SEVERITY_RANK[group.maxSeverity] ?? 0)) {
      group.maxSeverity = sev;
    }
  }
  return Array.from(map.values()).sort(
    (a, b) =>
      (SEVERITY_RANK[b.maxSeverity] ?? 0) - (SEVERITY_RANK[a.maxSeverity] ?? 0) ||
      b.totalHigh - a.totalHigh,
  );
}

export function InspectionPdfDocument({ data }: { data: InspectionPdfData }) {
  const damage = data.damage;
  const locations = (damage?.locations ?? []).filter((l) => l.snapshot);
  const groups = groupByPart(locations);
  const total = damage?.total_estimated_repair_cost ?? null;
  const odometerValue =
    typeof data.odometer?.value === "number" ? data.odometer.value.toLocaleString() : "—";

  return (
    <Document>
      <Page size="A4" style={styles.page}>
        <View style={styles.header}>
          <View>
            <Text style={styles.brand}>Vehicle Inspection Report</Text>
            <Text style={styles.subtitle}>
              {data.vehicle?.brand || "Unknown make"} {data.vehicle?.model || ""}
              {data.vehicle?.year ? ` · ${data.vehicle.year}` : ""}
            </Text>
          </View>
          <View>
            <Text style={styles.meta}>Inspection ID</Text>
            <Text style={[styles.meta, { color: "#0f172a", fontWeight: "bold" }]}>
              {data.inspectionId}
            </Text>
            <Text style={styles.meta}>{data.generatedAt}</Text>
          </View>
        </View>

        {/* Vehicle identity card */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Vehicle</Text>
          <View style={styles.rowWrap}>
            <IdentityCell label="Type" value={data.vehicle?.type} />
            <IdentityCell label="Make" value={data.vehicle?.brand} />
            <IdentityCell label="Model" value={data.vehicle?.model} />
            <IdentityCell label="Year" value={data.vehicle?.year} />
            <IdentityCell label="Variant" value={data.vehicle?.variant} />
            <IdentityCell label="Color" value={data.vehicle?.color} />
            <IdentityCell label="VIN" value={data.vehicle?.vin} />
            <IdentityCell label="Registration" value={data.vehicle?.registration} />
            <IdentityCell label="Odometer" value={`${odometerValue} km`} />
          </View>
        </View>

        {/* Damage overview */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Damage Summary</Text>
          <View style={styles.badgeRow}>
            <Text style={[styles.badge, severityStyle(damage?.severity)]}>
              {(damage?.severity || "low").toUpperCase()}
            </Text>
            {total && (
              <Text style={{ fontSize: 10 }}>
                Estimated repair: <Text style={{ fontWeight: "bold" }}>{formatRange(total)}</Text>
                {total.has_unknowns ? " (some items un-priced)" : ""}
              </Text>
            )}
          </View>

          {groups.length === 0 ? (
            <Text style={styles.empty}>No damage detected at the report threshold.</Text>
          ) : (
            <View style={styles.table}>
              <View style={styles.tableHeader}>
                <Text style={[styles.th, styles.colPart]}>Part</Text>
                <Text style={[styles.th, styles.colCount]}>#</Text>
                <Text style={[styles.th, styles.colSeverity]}>Severity</Text>
                <Text style={[styles.th, styles.colTypes]}>Types</Text>
                <Text style={[styles.th, styles.colCost]}>Est. cost</Text>
              </View>
              {groups.map((g) => (
                <View key={g.part} style={styles.tableRow}>
                  <Text style={[styles.td, styles.colPart]}>{g.partLabel}</Text>
                  <Text style={[styles.td, styles.colCount]}>{g.locations.length}</Text>
                  <Text style={[styles.td, styles.colSeverity]}>{g.maxSeverity}</Text>
                  <Text style={[styles.td, styles.colTypes]}>{Array.from(g.types).join(", ")}</Text>
                  <Text style={[styles.td, styles.colCost]}>
                    {g.hasCost
                      ? formatRange({
                          low: g.totalLow,
                          high: g.totalHigh,
                          midpoint: (g.totalLow + g.totalHigh) / 2,
                          currency: g.currency,
                        })
                      : "—"}
                  </Text>
                </View>
              ))}
            </View>
          )}
        </View>

        <View style={styles.footer} fixed>
          <Text>Inspection {data.inspectionId}</Text>
          <Text
            render={({ pageNumber, totalPages }) =>
              `Page ${pageNumber} of ${totalPages}`
            }
          />
        </View>
      </Page>

      {/* Snapshot pages */}
      {groups.length > 0 && (
        <Page size="A4" style={styles.page} wrap>
          <Text style={styles.sectionTitle}>Damage Snapshots</Text>
          {groups.map((g) => (
            <View key={g.part} style={styles.section} wrap={false}>
              <View style={styles.badgeRow}>
                <Text style={[styles.badge, severityStyle(g.maxSeverity)]}>
                  {g.maxSeverity.toUpperCase()}
                </Text>
                <Text style={{ fontSize: 11, fontWeight: "bold" }}>{g.partLabel}</Text>
                {g.hasCost && (
                  <Text style={{ fontSize: 9, color: "#475569" }}>
                    {formatRange({
                      low: g.totalLow,
                      high: g.totalHigh,
                      midpoint: (g.totalLow + g.totalHigh) / 2,
                      currency: g.currency,
                    })}
                  </Text>
                )}
              </View>
              <View style={styles.snapshotRow}>
                {g.locations.map((loc, i) => {
                  if (!loc.snapshot) return null;
                  const pct = Math.round((loc.confidence || 0) * 100);
                  return (
                    <View key={`${loc.snapshot}-${i}`} style={styles.snapshot} wrap={false}>
                      <PdfImage src={snapshotUrl(data.backendBaseUrl, loc.snapshot)} style={styles.snapshotImage} />
                      <Text style={styles.snapshotMeta}>
                        {(loc.type || "damage").toString()} · {pct}%
                      </Text>
                      {loc.estimated_cost && (
                        <Text style={styles.snapshotSub}>
                          {formatRange(loc.estimated_cost)}
                        </Text>
                      )}
                      {loc.rationale && <Text style={styles.rationale}>“{loc.rationale}”</Text>}
                    </View>
                  );
                })}
              </View>
            </View>
          ))}
          <View style={styles.footer} fixed>
            <Text>Inspection {data.inspectionId}</Text>
            <Text
              render={({ pageNumber, totalPages }) =>
                `Page ${pageNumber} of ${totalPages}`
              }
            />
          </View>
        </Page>
      )}
    </Document>
  );
}

function IdentityCell({ label, value }: { label: string; value?: string | number }) {
  return (
    <View style={styles.card}>
      <Text style={styles.label}>{label}</Text>
      <Text style={styles.value}>{value ? String(value) : "—"}</Text>
    </View>
  );
}
