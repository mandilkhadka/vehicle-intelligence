"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import Image from "next/image";
import { AppShell } from "@/components/app-shell";
import { PageHeader } from "@/components/page-header";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Search, Filter, Eye, Loader2, AlertTriangle } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import Loading from "./loading";
import { getInspections } from "@/lib/api";
import { getApiErrorMessage } from "@/lib/api-error";
import {
  toInspectionListItem,
  type InspectionListItem,
} from "@/lib/inspection-summary";
import { StatusBadge, VerificationBadge } from "@/components/status-badge";

function getScoreColor(score: number) {
  if (score >= 80) return "text-emerald-500";
  if (score >= 60) return "text-accent";
  if (score > 0) return "text-destructive";
  return "text-muted-foreground";
}

type HistoryRow = InspectionListItem & { dateString: string; score: number };

function HistoryPageContent() {
  const [searchQuery, setSearchQuery] = useState("");
  const [inspections, setInspections] = useState<HistoryRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filterStatus, setFilterStatus] = useState("all");
  // Forces this page into the Suspense boundary so static prerendering
  // doesn't choke on client-only search params.
  useSearchParams();

  const fetchInspections = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getInspections();
      const transformed = data.map((insp: any): HistoryRow => {
        const item = toInspectionListItem(insp);
        return {
          ...item,
          dateString: item.date ? item.date.toLocaleDateString() : "",
          score: Math.round(item.confidence * 100),
        };
      });
      setInspections(transformed);
    } catch (err) {
      console.error("Failed to fetch inspections:", err);
      setError(getApiErrorMessage(err, "Failed to load inspections"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchInspections();
  }, [fetchInspections]);

  const filteredInspections = inspections.filter((insp) => {
    const matchesSearch =
      insp.vehicle.toLowerCase().includes(searchQuery.toLowerCase()) ||
      insp.id.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesFilter =
      filterStatus === "all" || insp.status === filterStatus;
    return matchesSearch && matchesFilter;
  });

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
                <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <CardTitle>All Inspections</CardTitle>
                    <CardDescription>
                      {loading
                        ? "Loading..."
                        : error
                          ? "Unable to load inspections"
                          : `${filteredInspections.length} total inspections`}
                    </CardDescription>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="relative">
                      <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                      <Input
                        placeholder="Search inspections..."
                        className="w-full bg-secondary pl-10 sm:w-64"
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                      />
                    </div>
                    <Select
                      value={filterStatus}
                      onValueChange={setFilterStatus}
                    >
                      <SelectTrigger className="w-32">
                        <Filter className="mr-2 h-4 w-4" />
                        <SelectValue placeholder="Filter" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="all">All</SelectItem>
                        <SelectItem value="completed">Completed</SelectItem>
                        <SelectItem value="processing">Processing</SelectItem>
                        <SelectItem value="failed">Failed</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="w-40">ID</TableHead>
                        <TableHead>Vehicle</TableHead>
                        <TableHead>Date</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead className="text-center">Issues</TableHead>
                        <TableHead className="text-center">Score</TableHead>
                        <TableHead>Verification</TableHead>
                        <TableHead className="w-20"></TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {loading ? (
                        <TableRow>
                          <TableCell colSpan={8} className="text-center py-8">
                            <Loader2 className="h-6 w-6 animate-spin mx-auto text-primary mb-2" />
                            <p className="text-muted-foreground">
                              Loading inspections...
                            </p>
                          </TableCell>
                        </TableRow>
                      ) : error ? (
                        <TableRow>
                          <TableCell colSpan={8} className="text-center py-8">
                            <AlertTriangle className="mx-auto mb-2 h-6 w-6 text-destructive" />
                            <p className="mb-3 text-sm text-destructive">{error}</p>
                            <Button variant="outline" size="sm" onClick={fetchInspections}>
                              Retry
                            </Button>
                          </TableCell>
                        </TableRow>
                      ) : filteredInspections.length === 0 ? (
                        <TableRow>
                          <TableCell
                            colSpan={8}
                            className="text-center py-8 text-muted-foreground"
                          >
                            No inspections found
                          </TableCell>
                        </TableRow>
                      ) : (
                        filteredInspections.map((inspection) => (
                          <TableRow key={inspection.id}>
                            <TableCell className="font-mono text-sm">
                              {inspection.id}
                            </TableCell>
                            <TableCell>
                              <div className="flex items-center gap-3">
                                {inspection.image ? (
                                  <div className="relative h-10 w-14 overflow-hidden rounded-lg">
                                    <Image
                                      src={
                                        inspection.image || "/placeholder.svg"
                                      }
                                      alt={inspection.vehicle}
                                      fill
                                      className="object-cover"
                                      unoptimized
                                    />
                                  </div>
                                ) : (
                                  <div className="flex h-10 w-14 items-center justify-center rounded-lg bg-secondary text-xs font-medium text-muted-foreground">
                                    {inspection.brand.slice(0, 2).toUpperCase()}
                                  </div>
                                )}
                                <span className="font-medium">
                                  {inspection.vehicle}
                                </span>
                              </div>
                            </TableCell>
                            <TableCell className="text-muted-foreground">
                              {inspection.dateString}
                            </TableCell>
                            <TableCell>
                              <StatusBadge status={inspection.status} />
                            </TableCell>
                            <TableCell className="text-center">
                              {inspection.issues > 0 ? (
                                <Badge variant="secondary">
                                  {inspection.issues}
                                </Badge>
                              ) : (
                                <span className="text-muted-foreground">-</span>
                              )}
                            </TableCell>
                            <TableCell className="text-center">
                              <span
                                className={`font-semibold ${getScoreColor(inspection.score)}`}
                              >
                                {inspection.score > 0 ? inspection.score : "-"}
                              </span>
                            </TableCell>
                            <TableCell>
                              <VerificationBadge state={inspection.auditState} showDetail />
                            </TableCell>
                            <TableCell>
                              <Button variant="ghost" size="icon" asChild>
                                <Link
                                  href={`/inspection/${inspection.id}`}
                                  aria-label={`View inspection ${inspection.id}`}
                                >
                                  <Eye className="h-4 w-4" />
                                </Link>
                              </Button>
                            </TableCell>
                          </TableRow>
                        ))
                      )}
                    </TableBody>
                  </Table>
                </div>

              </CardContent>
            </Card>
      </div>
    </AppShell>
  );
}

export default function HistoryPage() {
  return (
    <Suspense fallback={<Loading />}>
      <HistoryPageContent />
    </Suspense>
  );
}
