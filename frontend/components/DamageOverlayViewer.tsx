"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Minus, Plus, RotateCcw, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export interface OverlayLocation {
  type?: string;
  part_label?: string;
  confidence?: number;
  severity?: string;
  frame?: string;
  bbox?: [number, number, number, number];
  mask?: Array<[number, number]>;
  frame_width?: number;
  frame_height?: number;
  source?: string;
}

interface DamageOverlayViewerProps {
  location: OverlayLocation;
  frameSrc: string;
  onClose: () => void;
}

const MIN_ZOOM = 1;
const MAX_ZOOM = 5;

/**
 * Full-frame damage viewer: renders the source frame with the detection's
 * bounding box (and segmentation mask, when the damage model provides one)
 * as an SVG overlay, with zoom centered on the damage.
 */
export default function DamageOverlayViewer({ location, frameSrc, onClose }: DamageOverlayViewerProps) {
  const [zoom, setZoom] = useState(1);
  const [natural, setNatural] = useState<{ w: number; h: number } | null>(null);
  const closeButtonRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // Dialog focus management: move focus to the close button on open and
  // hand it back to the opener on close.
  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    closeButtonRef.current?.focus();
    return () => {
      opener?.focus?.();
    };
  }, []);

  const frameW = location.frame_width || natural?.w || 0;
  const frameH = location.frame_height || natural?.h || 0;
  const bbox = location.bbox;
  const hasGeometry = frameW > 0 && frameH > 0;

  // Zoom toward the damage: keep the bbox center as the transform origin.
  const originX = bbox && frameW ? ((bbox[0] + bbox[2]) / 2 / frameW) * 100 : 50;
  const originY = bbox && frameH ? ((bbox[1] + bbox[3]) / 2 / frameH) * 100 : 50;

  const changeZoom = useCallback(
    (delta: number) => setZoom((z) => Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, Math.round((z + delta) * 2) / 2))),
    [],
  );

  const pct = Math.round((location.confidence || 0) * 100);
  const type = location.type || "damage";
  const maskPoints = (location.mask || [])
    .map(([x, y]) => `${(x * frameW).toFixed(1)},${(y * frameH).toFixed(1)}`)
    .join(" ");

  return (
    <div
      className="fixed inset-0 z-50 flex flex-col bg-black/85 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label={`${type} detection on full frame`}
      onClick={onClose}
    >
      <div
        className="flex items-center justify-between gap-3 px-4 py-3"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex min-w-0 items-center gap-2 text-sm text-white">
          <span className="font-medium capitalize">{type}</span>
          {location.part_label && (
            <span className="truncate text-white/70 capitalize">· {location.part_label}</span>
          )}
          <Badge variant="outline" className="border-white/30 text-white">
            {pct}%
          </Badge>
          {location.severity && (
            <Badge variant="outline" className="border-white/30 text-white uppercase">
              {location.severity}
            </Badge>
          )}
          {location.source && (
            <span className="hidden text-xs text-white/50 sm:inline">
              {location.source === "detector" ? "damage model" : location.source}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1">
          <ViewerButton label="Zoom out" onClick={() => changeZoom(-0.5)} disabled={zoom <= MIN_ZOOM}>
            <Minus className="h-4 w-4" />
          </ViewerButton>
          <span className="w-12 text-center font-mono text-xs text-white/80">{zoom.toFixed(1)}x</span>
          <ViewerButton label="Zoom in" onClick={() => changeZoom(0.5)} disabled={zoom >= MAX_ZOOM}>
            <Plus className="h-4 w-4" />
          </ViewerButton>
          <ViewerButton label="Reset zoom" onClick={() => setZoom(1)} disabled={zoom === 1}>
            <RotateCcw className="h-4 w-4" />
          </ViewerButton>
          <ViewerButton ref={closeButtonRef} label="Close viewer" onClick={onClose}>
            <X className="h-4 w-4" />
          </ViewerButton>
        </div>
      </div>

      <div className="flex flex-1 items-center justify-center overflow-hidden p-4">
        <div
          className="relative max-h-full max-w-full overflow-hidden rounded-lg"
          onClick={(e) => e.stopPropagation()}
        >
          <div
            className="relative transition-transform duration-200"
            style={{ transform: `scale(${zoom})`, transformOrigin: `${originX}% ${originY}%` }}
          >
            {/* eslint-disable-next-line @next/next/no-img-element -- overlay needs natural pixel geometry, not next/image optimization */}
            <img
              src={frameSrc}
              alt={`Full frame with ${type} highlighted`}
              className="max-h-[80vh] w-auto max-w-full select-none"
              draggable={false}
              onLoad={(e) => {
                const img = e.currentTarget;
                setNatural({ w: img.naturalWidth, h: img.naturalHeight });
              }}
            />
            {hasGeometry && (
              <svg
                className="pointer-events-none absolute inset-0 h-full w-full"
                viewBox={`0 0 ${frameW} ${frameH}`}
                preserveAspectRatio="none"
              >
                {maskPoints && (
                  <polygon
                    points={maskPoints}
                    className="fill-red-500/25 stroke-red-400"
                    strokeWidth={Math.max(1.5, frameW / 500)}
                    vectorEffect="non-scaling-stroke"
                  />
                )}
                {bbox && (
                  <rect
                    x={bbox[0]}
                    y={bbox[1]}
                    width={bbox[2] - bbox[0]}
                    height={bbox[3] - bbox[1]}
                    className="fill-none stroke-red-500"
                    strokeWidth={Math.max(2, frameW / 400)}
                    vectorEffect="non-scaling-stroke"
                  />
                )}
                {bbox && (
                  <text
                    x={bbox[0]}
                    y={Math.max(14, bbox[1] - 6)}
                    className="fill-red-400 text-[16px] font-semibold"
                    style={{ fontSize: Math.max(14, frameW / 60) }}
                  >
                    {type} {pct}%
                  </text>
                )}
              </svg>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function ViewerButton({
  ref,
  label,
  onClick,
  disabled,
  children,
}: {
  ref?: React.Ref<HTMLButtonElement>;
  label: string;
  onClick: () => void;
  disabled?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      ref={ref}
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "flex h-8 w-8 items-center justify-center rounded-md border border-white/20 text-white transition",
        disabled ? "opacity-40" : "hover:bg-white/10",
      )}
    >
      {children}
    </button>
  );
}
