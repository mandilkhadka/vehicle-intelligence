"use client";

import Image from "next/image";
import { AlertTriangle } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { BACKEND_BASE_URL } from "@/lib/api";

interface ExhaustInfoProps {
  exhaust?: {
    type?: string;
    confidence?: number;
    exhaust_image_path?: string;
  };
}

export default function ExhaustInfo({ exhaust }: ExhaustInfoProps) {
  if (!exhaust) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Exhaust</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">No exhaust data available</p>
        </CardContent>
      </Card>
    );
  }

  const pct = Math.round((exhaust.confidence || 0) * 100);
  const isModified = exhaust.type === "modified";
  const imgPath = exhaust.exhaust_image_path
    ? exhaust.exhaust_image_path.startsWith("uploads/")
      ? exhaust.exhaust_image_path
      : `uploads/${exhaust.exhaust_image_path}`
    : null;

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle>Exhaust</CardTitle>
        <Badge
          variant="outline"
          className={
            isModified
              ? "border-amber-500/40 bg-amber-500/10 text-amber-600 dark:text-amber-400"
              : "border-emerald-500/40 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
          }
        >
          {exhaust.type ? exhaust.type.toUpperCase() : "UNKNOWN"}
        </Badge>
      </CardHeader>
      <CardContent className="space-y-4">
        <div>
          <div className="mb-1 flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Confidence</span>
            <span className="font-medium">{pct}%</span>
          </div>
          <Progress value={pct} className="h-1.5" />
        </div>

        {isModified && (
          <div className="flex items-start gap-2 rounded-md border border-amber-500/30 bg-amber-500/5 p-3 text-sm text-amber-700 dark:text-amber-400">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <span>Modified exhaust detected. Verify compliance with local regulations.</span>
          </div>
        )}

        {imgPath && (
          <div className="relative aspect-video overflow-hidden rounded-lg border border-border bg-secondary/40">
            <Image
              src={`${BACKEND_BASE_URL}/${imgPath}`}
              alt="Exhaust system"
              fill
              className="object-cover"
              sizes="(max-width: 768px) 100vw, 50vw"
              unoptimized
            />
          </div>
        )}
      </CardContent>
    </Card>
  );
}
