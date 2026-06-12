"use client"

import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

export interface IdentityMetadata {
  vehicle_brand: string
  vehicle_model: string
  vin: string
  registration: string
  vehicle_year: string
  vehicle_variant: string
  vehicle_type: string
  vehicle_category: string
}

export const EMPTY_IDENTITY: IdentityMetadata = {
  vehicle_brand: "",
  vehicle_model: "",
  vin: "",
  registration: "",
  vehicle_year: "",
  vehicle_variant: "",
  vehicle_type: "",
  vehicle_category: "",
}

/**
 * Build the optional vehicle-identity payload for the upload endpoints.
 * Returns undefined when every field is blank so callers can skip the
 * form fields entirely.
 */
export function identityPayload(metadata: IdentityMetadata) {
  const payload = {
    vehicle_identity_source: "upload_form",
    vehicle_brand: metadata.vehicle_brand.trim(),
    vehicle_model: metadata.vehicle_model.trim(),
    vin: metadata.vin.trim(),
    registration: metadata.registration.trim(),
    vehicle_year: metadata.vehicle_year.trim(),
    vehicle_variant: metadata.vehicle_variant.trim(),
    vehicle_type: metadata.vehicle_type.trim(),
    vehicle_category: metadata.vehicle_category.trim(),
  }
  const hasEvidence = Boolean(
    payload.vehicle_brand ||
      payload.vehicle_model ||
      payload.vin ||
      payload.registration ||
      payload.vehicle_year ||
      payload.vehicle_variant ||
      payload.vehicle_type ||
      payload.vehicle_category,
  )
  return hasEvidence ? payload : undefined
}

/**
 * The optional vehicle-identity form card shared by the video (/inspect)
 * and photo (/photos) upload flows. Purely presentational — callers own
 * the state.
 */
export function IdentityFields({
  value,
  onFieldChange,
}: {
  value: IdentityMetadata
  onFieldChange: (field: keyof IdentityMetadata, fieldValue: string) => void
}) {
  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <Field
          id="vehicle_brand"
          label="Make"
          value={value.vehicle_brand}
          onChange={(v) => onFieldChange("vehicle_brand", v)}
        />
        <Field
          id="vehicle_model"
          label="Model"
          value={value.vehicle_model}
          onChange={(v) => onFieldChange("vehicle_model", v)}
        />
        <Field
          id="vin"
          label="VIN / chassis"
          value={value.vin}
          onChange={(v) => onFieldChange("vin", v)}
        />
        <Field
          id="registration"
          label="Registration"
          value={value.registration}
          onChange={(v) => onFieldChange("registration", v)}
        />
        <Field
          id="vehicle_year"
          label="Year"
          value={value.vehicle_year}
          onChange={(v) => onFieldChange("vehicle_year", v)}
        />
        <Field
          id="vehicle_variant"
          label="Trim / variant"
          value={value.vehicle_variant}
          onChange={(v) => onFieldChange("vehicle_variant", v)}
        />
        <Field
          id="vehicle_type"
          label="Vehicle type"
          value={value.vehicle_type}
          onChange={(v) => onFieldChange("vehicle_type", v)}
        />
        <Field
          id="vehicle_category"
          label="Category"
          value={value.vehicle_category}
          onChange={(v) => onFieldChange("vehicle_category", v)}
        />
      </div>
    </div>
  )
}

function Field({
  id,
  label,
  value,
  onChange,
}: {
  id: keyof IdentityMetadata
  label: string
  value: string
  onChange: (value: string) => void
}) {
  return (
    <div className="space-y-2">
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </div>
  )
}
