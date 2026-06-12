/**
 * Export reviewer feedback into a YOLO-format training set.
 *
 * Usage:
 *   npx tsx scripts/export-training-set.ts --out ./training-set [--since 2026-01-01]
 *
 * What it produces:
 *   <out>/images/<file>.jpg     copy of the frame the bbox is on
 *   <out>/labels/<file>.txt     YOLO label: <class_id> <cx> <cy> <w> <h>
 *   <out>/classes.txt           ordered class list
 *   <out>/manifest.json         provenance for every row (inspection, source, etc.)
 *
 * The script is idempotent: rows already in manifest.json from a prior run
 * are skipped. Designed to be safe to call from CI on a cron.
 *
 * Sources:
 *   - confirmed verdicts on existing locations -> positive sample with the
 *     model's bbox (from damage_summary.locations[location_index].bbox).
 *   - false_positive / wrong_type verdicts -> we currently skip these for
 *     positive labels; they're available in manifest for hard-negative
 *     mining later.
 *   - missing-damage reports -> positive sample with the human-drawn bbox.
 */

import * as fs from "fs";
import * as path from "path";
import { initDatabase } from "../src/db/init";
import {
  exportFeedbackSince,
  type FeedbackExportRow,
} from "../src/models/feedback";

// Must match the `type` strings the ML pipeline emits for
// damage_summary.locations (_DAMAGE_LOCATION_TYPES in ml-service/src/api/process.py).
const TAXONOMY = [
  "scratch",
  "dent",
  "rust",
  "crack",
  "paint_damage",
  "wheel_damage",
  "broken_light",
  "missing_part",
  "panel_misalignment",
];

// Legacy/plural spellings that reviewers or older pipeline versions may have
// stored; map them onto the canonical taxonomy instead of dropping the row.
const TAXONOMY_ALIASES: Record<string, string> = {
  scratches: "scratch",
  dents: "dent",
  cracks: "crack",
  broken_lights: "broken_light",
  missing_parts: "missing_part",
};

interface CliArgs {
  out: string;
  since?: string;
  uploadsRoot: string;
  verbose: boolean;
}

function parseArgs(): CliArgs {
  const args: Record<string, string | boolean> = {};
  for (let i = 2; i < process.argv.length; i++) {
    const arg = process.argv[i];
    if (arg.startsWith("--")) {
      const next = process.argv[i + 1];
      if (next && !next.startsWith("--")) {
        args[arg.slice(2)] = next;
        i++;
      } else {
        args[arg.slice(2)] = true;
      }
    }
  }
  return {
    out: String(args.out ?? "./training-set"),
    since: typeof args.since === "string" ? args.since : undefined,
    uploadsRoot: String(args["uploads-root"] ?? path.join(process.cwd(), "uploads")),
    verbose: Boolean(args.verbose),
  };
}

interface ManifestEntry {
  feedback_id: string;
  inspection_id: string;
  source: "feedback" | "missing";
  class_name: string;
  class_id: number;
  image: string;
  label: string;
  bbox: [number, number, number, number];
  added_at: string;
  reviewer?: string;
  note?: string;
}

interface Manifest {
  generated_at: string;
  classes: string[];
  entries: ManifestEntry[];
}

function readManifest(outDir: string): Manifest {
  const file = path.join(outDir, "manifest.json");
  if (!fs.existsSync(file)) {
    return { generated_at: new Date().toISOString(), classes: TAXONOMY, entries: [] };
  }
  try {
    const data = JSON.parse(fs.readFileSync(file, "utf-8")) as Manifest;
    return {
      generated_at: data.generated_at,
      classes: data.classes ?? TAXONOMY,
      entries: data.entries ?? [],
    };
  } catch {
    return { generated_at: new Date().toISOString(), classes: TAXONOMY, entries: [] };
  }
}

function writeManifest(outDir: string, manifest: Manifest): void {
  manifest.generated_at = new Date().toISOString();
  fs.writeFileSync(
    path.join(outDir, "manifest.json"),
    JSON.stringify(manifest, null, 2),
    "utf-8",
  );
}

function ensureDirs(outDir: string): void {
  fs.mkdirSync(path.join(outDir, "images"), { recursive: true });
  fs.mkdirSync(path.join(outDir, "labels"), { recursive: true });
}

function classIdFor(name?: string): number {
  if (!name) return -1;
  const normalized = name.toLowerCase();
  return TAXONOMY.indexOf(TAXONOMY_ALIASES[normalized] ?? normalized);
}

function resolveImageOnDisk(relPath: string | undefined, uploadsRoot: string): string | null {
  if (!relPath) return null;
  if (path.isAbsolute(relPath)) {
    return fs.existsSync(relPath) ? relPath : null;
  }
  const candidate = path.join(uploadsRoot, relPath.replace(/^uploads\//, ""));
  return fs.existsSync(candidate) ? candidate : null;
}

function imageDimensions(_imagePath: string): { width: number; height: number } | null {
  // We avoid pulling sharp / image-size as a build-time dep. YOLO labels are
  // normalized [0..1] so we need the source image dimensions. For PNG/JPEG
  // we can parse the header inline.
  try {
    const fd = fs.openSync(_imagePath, "r");
    const buf = Buffer.alloc(64);
    fs.readSync(fd, buf, 0, 64, 0);
    fs.closeSync(fd);

    // JPEG
    if (buf[0] === 0xff && buf[1] === 0xd8) {
      return readJpegDimensions(_imagePath);
    }
    // PNG
    if (buf.slice(0, 8).equals(Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]))) {
      const width = buf.readUInt32BE(16);
      const height = buf.readUInt32BE(20);
      return { width, height };
    }
  } catch {
    return null;
  }
  return null;
}

function readJpegDimensions(filePath: string): { width: number; height: number } | null {
  // Walk JPEG segments until SOFn. JPEG SOF markers: 0xC0..0xCF except
  // 0xC4 (DHT), 0xC8 (JPG), 0xCC (DAC).
  const fd = fs.openSync(filePath, "r");
  try {
    const stat = fs.fstatSync(fd);
    const buf = Buffer.alloc(Math.min(stat.size, 1 << 20));
    fs.readSync(fd, buf, 0, buf.length, 0);
    let i = 2; // skip SOI
    while (i < buf.length - 1) {
      if (buf[i] !== 0xff) {
        i++;
        continue;
      }
      const marker = buf[i + 1];
      if (
        marker >= 0xc0 &&
        marker <= 0xcf &&
        marker !== 0xc4 &&
        marker !== 0xc8 &&
        marker !== 0xcc
      ) {
        const height = buf.readUInt16BE(i + 5);
        const width = buf.readUInt16BE(i + 7);
        return { width, height };
      }
      const segLen = buf.readUInt16BE(i + 2);
      i += 2 + segLen;
    }
  } catch {
    return null;
  } finally {
    fs.closeSync(fd);
  }
  return null;
}

function yoloLine(
  classId: number,
  bbox: [number, number, number, number],
  width: number,
  height: number,
): string {
  const [x1, y1, x2, y2] = bbox;
  const cx = ((x1 + x2) / 2) / width;
  const cy = ((y1 + y2) / 2) / height;
  const w = Math.abs(x2 - x1) / width;
  const h = Math.abs(y2 - y1) / height;
  return `${classId} ${cx.toFixed(6)} ${cy.toFixed(6)} ${w.toFixed(6)} ${h.toFixed(6)}`;
}

function safeName(s: string): string {
  return s.replace(/[^A-Za-z0-9._-]/g, "_");
}

interface PreparedRow {
  classId: number;
  className: string;
  framePathOnDisk: string;
  bbox: [number, number, number, number];
}

function prepareFromConfirmedFeedback(row: FeedbackExportRow, uploadsRoot: string): PreparedRow | null {
  if (row.verdict !== "confirmed") return null;
  if (!row.damage_summary) return null;
  let summary: any;
  try {
    summary = JSON.parse(row.damage_summary);
  } catch {
    return null;
  }
  const locations = Array.isArray(summary?.locations) ? summary.locations : [];
  if (row.location_index === undefined || row.location_index === null) return null;
  const loc = locations[row.location_index];
  if (!loc || !Array.isArray(loc.bbox) || loc.bbox.length < 4) return null;
  const className = (row.corrected_type || loc.type || "").toLowerCase();
  const classId = classIdFor(className);
  if (classId < 0) return null;
  const framePath = resolveImageOnDisk(loc.frame || loc.snapshot, uploadsRoot);
  if (!framePath) return null;
  return {
    classId,
    className,
    framePathOnDisk: framePath,
    bbox: [Number(loc.bbox[0]), Number(loc.bbox[1]), Number(loc.bbox[2]), Number(loc.bbox[3])],
  };
}

function prepareFromMissing(row: FeedbackExportRow, uploadsRoot: string): PreparedRow | null {
  if (row.source !== "missing") return null;
  if (!row.bbox) return null;
  let bbox: number[];
  try {
    bbox = JSON.parse(row.bbox);
  } catch {
    return null;
  }
  if (!Array.isArray(bbox) || bbox.length < 4) return null;
  const className = (row.reported_type || "").toLowerCase();
  const classId = classIdFor(className);
  if (classId < 0) return null;
  const framePath = resolveImageOnDisk(row.frame_path, uploadsRoot);
  if (!framePath) return null;
  return {
    classId,
    className,
    framePathOnDisk: framePath,
    bbox: [Number(bbox[0]), Number(bbox[1]), Number(bbox[2]), Number(bbox[3])],
  };
}

function main(): void {
  const args = parseArgs();
  ensureDirs(args.out);
  initDatabase();

  const manifest = readManifest(args.out);
  const seen = new Set(manifest.entries.map((e) => e.feedback_id));

  fs.writeFileSync(
    path.join(args.out, "classes.txt"),
    TAXONOMY.join("\n") + "\n",
    "utf-8",
  );

  const rows = exportFeedbackSince(args.since);
  let added = 0;
  let skipped = 0;
  let failed = 0;

  for (const row of rows) {
    if (seen.has(row.feedback_id)) {
      skipped++;
      continue;
    }
    const prepared =
      row.source === "feedback"
        ? prepareFromConfirmedFeedback(row, args.uploadsRoot)
        : prepareFromMissing(row, args.uploadsRoot);
    if (!prepared) {
      failed++;
      if (args.verbose) {
        console.log(`skip ${row.feedback_id} (${row.source}) — not usable as training row`);
      }
      continue;
    }

    const dims = imageDimensions(prepared.framePathOnDisk);
    if (!dims || dims.width <= 0 || dims.height <= 0) {
      failed++;
      if (args.verbose) {
        console.log(`skip ${row.feedback_id} — could not read image dimensions`);
      }
      continue;
    }

    const stem = safeName(
      `${row.inspection_id}_${row.feedback_id.slice(0, 8)}_${prepared.className}`,
    );
    const imageOut = path.join(args.out, "images", `${stem}.jpg`);
    const labelOut = path.join(args.out, "labels", `${stem}.txt`);

    try {
      fs.copyFileSync(prepared.framePathOnDisk, imageOut);
    } catch (err) {
      failed++;
      if (args.verbose) console.log(`skip ${row.feedback_id} — copy failed: ${(err as Error).message}`);
      continue;
    }
    fs.writeFileSync(
      labelOut,
      yoloLine(prepared.classId, prepared.bbox, dims.width, dims.height) + "\n",
      "utf-8",
    );

    manifest.entries.push({
      feedback_id: row.feedback_id,
      inspection_id: row.inspection_id,
      source: row.source,
      class_name: prepared.className,
      class_id: prepared.classId,
      image: path.relative(args.out, imageOut),
      label: path.relative(args.out, labelOut),
      bbox: prepared.bbox,
      added_at: new Date().toISOString(),
      reviewer: row.reviewer ?? undefined,
      note: row.note ?? undefined,
    });
    added++;
  }

  writeManifest(args.out, manifest);
  console.log(
    `Training set updated at ${args.out}: +${added}, ${skipped} already exported, ${failed} skipped.`,
  );
}

main();
