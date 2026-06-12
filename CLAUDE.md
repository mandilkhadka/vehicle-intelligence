# CLAUDE.md

Guidance for Claude Code (claude.ai/code) when working in this repository.

## System overview

Vehicle Intelligence Platform (VIP) is a 3-service system that ingests a 360°
vehicle video and emits a structured inspection report (identity, odometer,
part-grounded damage with cost + rationale, exhaust). The services run
independently and talk over HTTP.

- **frontend/** — Next.js 16 + React 19 + Tailwind 4 (port 3000). Upload,
  guided capture, polling, results, reviewer queue, PDF render.
- **backend/** — Node + Express + TypeScript + `better-sqlite3` (port 3001).
  Persistence, upload pipeline, ML orchestration, reaper + sweeper jobs,
  feedback API.
- **ml-service/** — Python + FastAPI (port 8000). All model inference (YOLOv8,
  CLIP, PaddleOCR, Gemini, OpenAI vision).

Shared TypeScript types live in `shared/types.ts`. Keep enums (`JobStatus`,
`VehicleType`, `DamageInfo`, …) in sync with `backend/src/db/schema.sql` when
modifying.

## Request lifecycle

Read this before changing the pipeline.

1. *(Optional)* Frontend `POST /api/upload/preflight` → backend writes the
   video to a transient `uploads/preflight/` dir, forwards to ML
   `/api/preflight`, deletes the file regardless of outcome. **Fails open**:
   ML errors return `{ ok: true, can_proceed: true, warnings: [...] }`.
2. `POST /api/upload` → backend stores the video in `backend/uploads/videos/`,
   inserts a `files` row + a `jobs` row (status `pending`), returns `jobId`.
3. `backend/src/services/job_processor.ts` runs the job **in-process** (no
   queue). It POSTs the absolute video path to ML `/api/process` with
   retry/backoff (`isRetryableError` covers ECONNREFUSED / 5xx; see
   `RETRY_CONFIG`).
4. ML pipeline (`src/api/process.py`):
   `FrameExtractor` →
   `VehicleIdentifier` (CLIP) →
   `DashboardDetector` + `OdometerReader` (YOLO + PaddleOCR + VLM chain) →
   `DamageDetector` →
   `panel_inference.attach_parts_to_locations` →
   `repair_costs.estimate_repair_costs` →
   `damage_rationale.attach_rationales` (best-effort, batched VLM) →
   `ExhaustClassifier` →
   `ReportGenerator` (Gemini, with text fallback).

   Models load **once at startup** via `ModelRegistry` (singleton on
   `app.state`). Do not re-instantiate per request. Each stage is wrapped by
   `_run_stage()` with a per-stage timeout (env: `ML_STAGE_TIMEOUT_*`).
5. Backend Zod-validates the ML response, writes results into `inspections`,
   flips the job to `completed`. On validation failure the uploaded video is
   deleted. Frontend polls `GET /api/jobs/:id`, then fetches
   `GET /api/inspections/:id`.

Path crossing between services is awkward: ML receives an absolute path and
writes outputs under `backend/uploads/{frames,odometer_images}/`.
`convert_to_relative_path` in `process.py` and `path_validator.py` convert
between absolute disk paths and the relative paths the backend serves under
`/uploads`.

## Background jobs (backend)

Set up in `backend/src/index.ts`:

- **Startup reaper** — `reapStuckJobs()` runs once on boot.
- **5-minute interval reaper** — marks jobs failed if they've been
  `processing` past `STUCK_PROCESSING_MAX_MINUTES` or `pending` past
  `STUCK_PENDING_MAX_MINUTES`.
- **6-hour video sweeper** — deletes raw videos for completed jobs older than
  `VIDEO_RETENTION_DAYS`.

These exist because job processing is in-process: a backend restart abandons
running jobs; the reaper picks up the pieces on next boot.

## API surface

### Backend (port 3001)

Inspection lifecycle:
- `POST /api/upload/preflight`, `POST /api/upload`, `GET /api/jobs/:id`
- `POST /api/upload/photos` — photo flow: 1–24 pictures (`photos` field,
  JPG/PNG/WEBP only — no HEIC, OpenCV can't decode it) stored in
  `uploads/photos/<jobId>/`; ML uses them directly as frames (no extraction)
- `GET /api/inspections`, `GET /api/inspections/:id`
- `PUT /api/inspections/:id/identity`, `PUT /api/inspections/:id/vlm`,
  `POST /api/inspections/:id/retry-vlm`

Active-learning feedback (all under `/api`):
- `POST/GET/DELETE /inspections/:id/feedback`
- `POST/GET/DELETE /inspections/:id/missing-damage`
- `GET /feedback/export?since=ISO`
- `GET /feedback/review?limit=N`

Other:
- `GET /api/metrics`, `GET /health`
- `/uploads/frames/*` + `/uploads/odometer_images/*` (guarded). Raw videos
  are explicitly **403**.

### ML service (port 8000)

- `POST /api/preflight` — 12-frame sample, returns blur + brightness +
  vehicle-presence diagnostics.
- `POST /api/process` — full inspection pipeline. Takes exactly one of
  `video_path` (frames extracted) or `image_paths` (photo flow: uploaded
  pictures are normalized into the frames dir and used as-is).
- `POST /api/retry-vlm` — VLM-only rerun from saved organized frames.
- `GET /health`, `GET /ready` (pass
  `?live_gemini=true&live_openai=true&live_ollama=true` for VLM provider
  verification — `live_ollama` confirms the server is up and the models are
  pulled).

## Static file access control

`backend/src/index.ts` mounts `/uploads` with a prefix guard:

- `/uploads/frames/*` and `/uploads/odometer_images/*` are served.
- Everything else under `/uploads/` is **403** — including raw videos.

If you add a new artifact directory, add its prefix to `allowedPrefixes` in
`index.ts` or it will be blocked.

## Common commands

```bash
# all three at once — handles port-clearing, venv, deps
./START_SERVICES.sh
# logs in /tmp/vi-{backend,ml-service,frontend}.log; Ctrl+C kills all

# backend
cd backend
npm run dev          # tsx watch (3001)
npm run build        # tsc → dist/
npm run type-check
npm run lint

# frontend
cd frontend
npm run dev          # next dev (3000)
npm run build
npm run lint
npm test             # jest (jsdom)
npm run test:e2e     # playwright
npx jest path/to/file.test.tsx

# ml-service
cd ml-service && source venv/bin/activate
python src/main.py   # uvicorn (8000)
pytest tests/
pytest tests/integration/test_ml_pipeline.py::TestX::test_y
```

Docker: `docker-compose up` (dev) or `docker-compose -f docker-compose.prod.yml up` (prod).

## Operational scripts

```bash
# Backend — export reviewer feedback as a YOLO training set (idempotent).
cd backend
npx tsx scripts/export-training-set.ts --out ./training-set [--since 2026-01-01]
# Outputs: images/, labels/, classes.txt, manifest.json. Manifest tracks
# already-exported feedback_ids so reruns are safe.

# ML — pipeline readiness, per-video completion audit, VLM retry.
cd ml-service
python scripts/check_pipeline_readiness.py --live-gemini --live-openai --json > /tmp/vip-readiness.json
python scripts/evaluate_video_understanding.py ../360.mov --with-models --read-odometer \
  --output-dir /tmp/vip-video-eval
python scripts/audit_pipeline_completion.py \
  --manifest /tmp/vip-video-eval/frame_analysis_manifest.json \
  --inspection-json /path/to/process_response.json \
  --readiness-json /tmp/vip-readiness.json
python scripts/retry_vlm_analysis.py \
  --inspection-json /path/to/inspection.json \
  --output-json /tmp/vip-vlm-retry.json \
  --merged-output-json /tmp/vip-process-response-with-vlm.json
```

## Testing notes

- **Frontend** — Jest + Testing Library (`next/jest` in `frontend/jest.config.js`).
  Tests in `frontend/__tests__/`. Playwright suite in `frontend/e2e/`.
- **ML service** — pytest. `tests/conftest.py` sets `SRC_DIR` on `sys.path`;
  integration tests in `tests/integration/` exercise the FastAPI app.
- **Backend** — test files exist under `backend/src/__tests__/` (integration +
  e2e) **but `backend/package.json` has no `test` script and no Jest
  dependency**. They are spec scaffolds. Do not assume `npm test` works in
  backend; wire up Jest first.

## Frontend layout

- `app/` — App Router pages: `/`, `/inspect`, `/capture`, `/job/[id]`,
  `/inspection/[id]`, `/review`, `/history`.
- `components/` — feature components (`DamageInfo`, `JobStatus`,
  `InspectionPdfDocument`, …). `components/ui/` is shadcn-style primitives.
- `lib/api.ts` — typed client. The frontend never calls the ML service
  directly.
- `next.config.js` — Permissions-Policy is set to `camera=(self)` so
  `/capture` can prompt for the camera. `/uploads/*` is rewritten to
  `BACKEND_URL` so `next/image` can load snapshots locally without remote
  host whitelisting.

## Conventions / gotchas

- The backend uses **synchronous** `better-sqlite3` — no `await` on DB calls.
  Schema is applied from `src/db/schema.sql`; newer tables
  (`damage_feedback`, `damage_missing_reports`) are `CREATE TABLE IF NOT
  EXISTS` migrations in `src/db/init.ts`. There is no migration tooling
  beyond that.
- Job processing is in-process. CPU/GPU work happens in the ML service;
  backend just orchestrates and persists. **Don't move ML logic into the
  backend.**
- `ModelRegistry.initialize_all_models()` runs at FastAPI startup
  (`lifespan`). If startup fails the service refuses to start by design —
  don't catch and continue.
- The frontend talks to the backend via `NEXT_PUBLIC_API_URL`
  (default `http://localhost:3001/api`). The frontend never calls the ML
  service directly.
- Rate limit + helmet CSP are configured in `backend/src/index.ts`; CORS
  origins come from `config.cors.allowedOrigins` (env
  `CORS_ALLOWED_ORIGINS`).
- `JobStatus` and other enums in `shared/types.ts` must match the strings
  used in `schema.sql` and `models/inspection.ts`.
- Feedback is keyed by `(inspection_id, location_index)` — positional index
  into `damage_summary.locations`. Damage UUIDs are not stable across
  pipeline versions; the index is.
- The damage class taxonomy lives in **two places** that must stay in sync:
  the ML pipeline's emitted `type` strings and `TAXONOMY` in
  `backend/scripts/export-training-set.ts`. The export script silently
  drops feedback rows whose class isn't in `TAXONOMY`.

## Environment variables

**Backend** (`.env`): `PORT`, `ML_SERVICE_URL`, `ML_SERVICE_TIMEOUT_MS`,
`DATABASE_PATH`, `UPLOAD_MAX_SIZE`, `CORS_ALLOWED_ORIGINS`,
`RATE_LIMIT_WINDOW_MS`, `RATE_LIMIT_MAX_REQUESTS`, `VIDEO_RETENTION_DAYS`,
`LOG_LEVEL`.

**ML service** (`.env`): `GEMINI_API_KEY` (optional; report text falls back
without it), `OPENAI_API_KEY` (optional fallback), `OPENAI_BASE_URL`,
`OLLAMA_BASE_URL` (optional local VLM — when set, Ollama is the **primary**
provider, tried before Gemini/OpenAI), `OLLAMA_VISION_MODEL` (default
`qwen2.5vl`), `OLLAMA_TEXT_MODEL` (default `gemma2:9b`), `OLLAMA_TIMEOUT_SECONDS`,
`ML_DEVICE` (auto/`cuda`/`mps`/`cpu`), `ML_YOLO_MODEL` / `ML_CLIP_MODEL`
(model weights are never hardcoded — see `src/config/constants.py`),
`ML_DAMAGE_MODEL_PATH` / `_ARCH` / `_CONFIDENCE` / `_IOU` / `_IMGSZ` /
`ML_DAMAGE_CLASS_MAP` (dedicated damage detector), `ML_STAGE_TIMEOUT_VEHICLE` /
`_ODOMETER` / `_DAMAGE` / `_EXHAUST` / `_GEMINI`,
`ML_DAMAGE_RATIONALE_TIMEOUT`, `PORT`, `LOG_LEVEL`, `CORS_ALLOWED_ORIGINS`.

The VLM provider chain is **Ollama → Gemini → OpenAI** (first one configured
*and* successful wins). Ollama uses its **native** `/api/chat` endpoint
(`src/services/ollama_client.py`) with `format: "json"` — not the OpenAI-compat
`/v1` shim, which fails on vision because Ollama lacks the `/v1/responses` API.
The chain is shared by `gemini_analyzer.py` (visual analysis), `report_generator.py`
(text), `odometer_reader.py` (VLM odometer), and `damage_rationale.py` (via
`GeminiAnalyzer.vlm_generate_text`).

Damage detection sources, in priority order. CLIP is **never** a damage
source — it only does frame selection and vehicle identification.

1. **Dedicated detector (primary when configured)** — set
   `ML_DAMAGE_MODEL_PATH` to detection/segmentation weights (e.g. CarDD-trained
   YOLO11/YOLO12 or RT-DETR; `ML_DAMAGE_MODEL_ARCH=auto|yolo|rtdetr`).
   `ModelRegistry` loads it at startup; `damage_model.py` maps model classes to
   the pipeline taxonomy (`ML_DAMAGE_CLASS_MAP` extends it) and emits locations
   with pixel `bbox`, optional normalized `mask` polygons,
   `frame_width`/`frame_height`, and `source: "detector"`. Train/benchmark/
   deploy workflow lives in `ml-service/training/` (prepare CarDD → train
   candidates → `benchmark_damage_models.py` ranks P/R/F1/mAP/small-instance
   recall/latency → point `ML_DAMAGE_MODEL_PATH` at the winner).
2. **VLM** (`gemini_analyzer.py`) — authoritative only when no detector is
   configured; otherwise a complementary source for categories outside the
   trained taxonomy (rust, missing parts, …). Findings are gated by
   `ML_DAMAGE_VLM_MIN_CONFIDENCE` (0.55), multi-frame consensus
   `ML_DAMAGE_CONSENSUS_MIN_FRAMES` (2; set 1 to disable), and a single-frame
   escape hatch `ML_DAMAGE_VLM_HIGH_CONFIDENCE` (0.85). Each VLM finding's
   normalized `region` is cropped into a `snapshot` + pixel `bbox` in
   `process.py` (`_ground_vlm_locations`). VLM findings duplicating a detector
   finding (same type/view, overlapping bbox) are dropped
   (`_dedupe_detector_vlm_overlaps`).
3. The classical OpenCV heuristics in `damage_detector.py` (which
   false-positive on clean cars) stay OFF — `ML_DAMAGE_USE_CV_HEURISTICS`
   (default `false`).

All sources emit the same location contract, so `panel_inference`,
`repair_costs`, and `damage_rationale` are source-agnostic.

**Frontend** (`.env.local`): `NEXT_PUBLIC_API_URL`, `BACKEND_URL` (used at
build time for `/uploads/*` rewrite).
