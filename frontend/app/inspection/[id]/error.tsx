"use client";

import { useEffect } from "react";
import Link from "next/link";
import { AlertTriangle } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function InspectionErrorBoundary({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Inspection page crashed:", error);
  }, [error]);

  return (
    <AppShell>
      <div className="p-4 sm:p-6 lg:p-8">
        <Card className="border-destructive/30">
          <CardHeader className="flex flex-row items-center gap-3">
            <AlertTriangle className="h-5 w-5 text-destructive" />
            <CardTitle>Something went wrong loading this inspection</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-muted-foreground">
              The inspection data may be incomplete or malformed. You can try again, or
              go back to the history list.
            </p>
            <pre className="overflow-auto rounded-md border bg-muted p-3 text-xs">
              {error.message}
            </pre>
            <div className="flex gap-2">
              <Button onClick={reset}>Try again</Button>
              <Button variant="outline" asChild>
                <Link href="/history">Back to history</Link>
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </AppShell>
  );
}
