"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";

interface VehicleInfoProps {
  vehicleInfo?: {
    type?: string;
    brand?: string;
    model?: string;
    year?: string;
    variant?: string;
    vehicle_category?: string;
    year_range?: string;
    generation?: string;
    variant_candidates?: string[];
    variant_candidate?: string;
    variant_confidence?: number;
    variant_candidates_ranked?: Array<{
      variant?: string;
      confidence?: number;
    }>;
    model_confidence?: number;
    model_candidates?: Array<{
      model?: string;
      confidence?: number;
    }>;
    identity_source?: string;
    identity_override_fields?: string[];
    vin?: string;
    registration?: string;
    identity_notes?: string;
    color?: string;
    confidence?: number;
  };
}

export default function VehicleInfo({ vehicleInfo }: VehicleInfoProps) {
  const modelCandidates = vehicleInfo?.model_candidates
    ?.filter((candidate) => candidate?.model)
    .slice(0, 5);
  const variantCandidates = vehicleInfo?.variant_candidates_ranked
    ?.filter((candidate) => candidate?.variant)
    .slice(0, 5);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Vehicle</CardTitle>
      </CardHeader>
      <CardContent>
        {!vehicleInfo ? (
          <p className="text-sm text-muted-foreground">No vehicle data available</p>
        ) : (
          <dl className="space-y-3 text-sm">
            <Row label="Type" value={vehicleInfo.type} capitalize />
            <Row label="Brand" value={vehicleInfo.brand} />
            <Row label="Model" value={vehicleInfo.model} />
            {vehicleInfo.year && <Row label="Year" value={vehicleInfo.year} />}
            {vehicleInfo.variant && <Row label="Variant" value={vehicleInfo.variant} />}
            {vehicleInfo.vehicle_category && (
              <Row label="Category candidate" value={vehicleInfo.vehicle_category} capitalize />
            )}
            {vehicleInfo.year_range && (
              <Row label="Year range candidate" value={vehicleInfo.year_range} />
            )}
            {vehicleInfo.generation && (
              <Row label="Generation candidate" value={vehicleInfo.generation} capitalize />
            )}
            {vehicleInfo.variant_candidates?.length ? (
              <Row label="Variant candidates" value={vehicleInfo.variant_candidates.join(", ")} />
            ) : null}
            {vehicleInfo.variant_candidate && (
              <Row label="Top variant candidate" value={vehicleInfo.variant_candidate} />
            )}
            {vehicleInfo.color && <Row label="Color" value={vehicleInfo.color} capitalize />}
            {vehicleInfo.identity_source && (
              <Row label="Identity source" value={formatIdentitySource(vehicleInfo.identity_source)} />
            )}
            {vehicleInfo.identity_override_fields?.length ? (
              <Row
                label="Verified fields"
                value={vehicleInfo.identity_override_fields.map(formatIdentitySource).join(", ")}
              />
            ) : null}
            {vehicleInfo.vin && <Row label="VIN / chassis" value={vehicleInfo.vin} />}
            {vehicleInfo.registration && <Row label="Registration" value={vehicleInfo.registration} />}
            <ConfidenceRow value={vehicleInfo.confidence} />
            {typeof vehicleInfo.variant_confidence === "number" && (
              <ConfidenceRow label="Variant candidate confidence" value={vehicleInfo.variant_confidence} />
            )}
            {typeof vehicleInfo.model_confidence === "number" && (
              <ConfidenceRow label="Model candidate confidence" value={vehicleInfo.model_confidence} />
            )}
            {variantCandidates?.length ? (
              <div className="space-y-1">
                <dt className="text-muted-foreground">Ranked variant candidates</dt>
                <dd className="flex flex-wrap gap-1.5">
                  {variantCandidates.map((candidate) => (
                    <span
                      key={candidate.variant}
                      className="rounded-md border border-border px-2 py-1 text-xs font-medium"
                    >
                      {candidate.variant}
                      {typeof candidate.confidence === "number"
                        ? ` ${Math.round(candidate.confidence * 100)}%`
                        : ""}
                    </span>
                  ))}
                </dd>
              </div>
            ) : null}
            {modelCandidates?.length ? (
              <div className="space-y-1">
                <dt className="text-muted-foreground">Model candidates</dt>
                <dd className="flex flex-wrap gap-1.5">
                  {modelCandidates.map((candidate) => (
                    <span
                      key={candidate.model}
                      className="rounded-md border border-border px-2 py-1 text-xs font-medium"
                    >
                      {candidate.model}
                      {typeof candidate.confidence === "number"
                        ? ` ${Math.round(candidate.confidence * 100)}%`
                        : ""}
                    </span>
                  ))}
                </dd>
              </div>
            ) : null}
            {vehicleInfo.identity_notes && (
              <div className="space-y-1">
                <dt className="text-muted-foreground">Identity notes</dt>
                <dd className="rounded-md bg-muted p-3 text-xs leading-relaxed text-muted-foreground">
                  {vehicleInfo.identity_notes}
                </dd>
              </div>
            )}
          </dl>
        )}
      </CardContent>
    </Card>
  );
}

function formatIdentitySource(value: string) {
  return value.replace(/_/g, " ");
}

function Row({ label, value, capitalize }: { label: string; value?: string; capitalize?: boolean }) {
  return (
    <div className="flex items-start justify-between gap-4">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className={`${capitalize ? "capitalize " : ""}max-w-[60%] break-words text-right font-medium`}>
        {value || "Unknown"}
      </dd>
    </div>
  );
}

function ConfidenceRow({ label = "Confidence", value }: { label?: string; value?: number }) {
  const pct = Math.round((value || 0) * 100);
  return (
    <div>
      <div className="mb-1 flex items-center justify-between">
        <dt className="text-muted-foreground">{label}</dt>
        <dd className="font-medium">{pct}%</dd>
      </div>
      <Progress value={pct} className="h-1.5" />
    </div>
  );
}
