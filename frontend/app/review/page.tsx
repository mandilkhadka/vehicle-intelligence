"use client";

/**
 * Active-learning review queue.
 *
 * Lists damage detections whose confidence is closest to 0.5 — the
 * model's most uncertain hits — across all inspections that don't yet
 * have feedback. Reviewers click through, confirm or reject, and the
 * feedback feeds the export endpoint that builds the training set.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { ExternalLink, Loader2, RefreshCcw, Tag, ThumbsDown, ThumbsUp } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  getReviewQueue,
  submitDamageFeedback,
  type FeedbackVerdict,
  type UncertainDetection,
} from "@/lib/api";
import { getApiErrorMessage } from "@/lib/api-error";
import { uploadSrc } from "@/lib/format";
import { cn } from "@/lib/utils";

export default function ReviewPage() {
  const [items, setItems] = useState<UncertainDetection[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pendingKey, setPendingKey] = useState<string | null>(null);
  const [reviewedKeys, setReviewedKeys] = useState<Set<string>>(new Set());

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getReviewQueue(150);
      setItems(data);
    } catch (err) {
      setError(getApiErrorMessage(err, "Failed to load review queue"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const review = useCallback(
    async (item: UncertainDetection, verdict: FeedbackVerdict) => {
      const key = `${item.inspection_id}:${item.location_index}`;
      setPendingKey(key);
      try {
        await submitDamageFeedback(item.inspection_id, {
          location_index: item.location_index,
          verdict,
        });
        setReviewedKeys((prev) => {
          const next = new Set(prev);
          next.add(key);
          return next;
        });
      } catch (err) {
        setError(getApiErrorMessage(err, "Failed to submit feedback"));
      } finally {
        setPendingKey(null);
      }
    },
    [],
  );

  const visibleItems = useMemo(
    () =>
      items.filter((i) => !reviewedKeys.has(`${i.inspection_id}:${i.location_index}`)),
    [items, reviewedKeys],
  );

  return (
    <AppShell>
      <div className="mx-auto max-w-6xl p-4 sm:p-6 lg:p-8">
        <PageHeader
          title="Review queue"
          description="The detections the model is least sure about. Confirm or reject — this feeds the next training run."
        >
          <Button variant="outline" onClick={load} disabled={loading} className="gap-2">
            <RefreshCcw className={cn("h-4 w-4", loading && "animate-spin")} /> Refresh
          </Button>
        </PageHeader>

        {error && (
          <div className="mb-4 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
            {error}
          </div>
        )}

        {loading && items.length === 0 && (
          <div className="flex items-center justify-center py-12 text-muted-foreground">
            <Loader2 className="mr-2 h-5 w-5 animate-spin" />
            Loading review queue…
          </div>
        )}

        {!loading && visibleItems.length === 0 && (
          <Card>
            <CardHeader>
              <CardTitle>All caught up</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                No uncertain detections waiting for review. New inspections will
                show up here as soon as the pipeline finishes them.
              </p>
            </CardContent>
          </Card>
        )}

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {visibleItems.map((item) => {
            const key = `${item.inspection_id}:${item.location_index}`;
            const src = uploadSrc(item.snapshot);
            const pct = Math.round(item.confidence * 100);
            const uncertainty = Math.round(item.uncertainty * 100);
            const isPending = pendingKey === key;
            return (
              <Card key={key} className="overflow-hidden">
                <div className="relative aspect-video bg-secondary">
                  {src ? (
                    <Image
                      src={src}
                      alt={`${item.type || "damage"} on ${item.part_label || item.part || "unknown area"}`}
                      fill
                      unoptimized
                      className="object-cover"
                      sizes="(max-width: 1024px) 50vw, 33vw"
                    />
                  ) : (
                    <div className="flex h-full items-center justify-center text-xs text-muted-foreground">
                      No snapshot
                    </div>
                  )}
                  <div className="absolute right-2 top-2 rounded-md bg-background/80 px-2 py-0.5 text-xs font-semibold backdrop-blur-sm">
                    {pct}% conf · ±{50 - uncertainty}
                  </div>
                </div>
                <CardContent className="space-y-3 p-4">
                  <div>
                    <div className="text-sm font-semibold capitalize">
                      {item.type || "damage"} on {item.part_label || item.part || "unknown area"}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      Severity: {item.severity || "—"} ·{" "}
                      <Link
                        href={`/inspection/${item.inspection_id}`}
                        className="inline-flex items-center gap-1 text-primary hover:underline"
                      >
                        Open inspection <ExternalLink className="h-3 w-3" />
                      </Link>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => review(item, "confirmed")}
                      disabled={isPending}
                      className="flex-1 gap-1"
                    >
                      {isPending ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <ThumbsUp className="h-4 w-4" />
                      )}
                      Confirm
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => review(item, "false_positive")}
                      disabled={isPending}
                      className="flex-1 gap-1"
                    >
                      <ThumbsDown className="h-4 w-4" />
                      Reject
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => review(item, "wrong_type")}
                      disabled={isPending}
                      className="gap-1"
                      title="Wrong damage type"
                    >
                      <Tag className="h-4 w-4" />
                      Wrong type
                    </Button>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      </div>
    </AppShell>
  );
}
