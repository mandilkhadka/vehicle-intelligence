# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## System Overview

Vehicle Intelligence Platform (VIP) is a 3-service MVP that ingests a 360° vehicle video and emits an inspection report (vehicle ID, odometer, damage, exhaust). The three services run independently and talk over HTTP:

- **frontend/** — Next.js 16 + React 19 + Tailwind 4 (port 3000). Uploads videos, polls jobs, renders results.
- **backend/** — Node + Express + TypeScript + SQLite via `better-sqlite3` (port 3001). Owns persistence, the upload pipeline, and orchestrates ML calls.
- **ml-service/** — Python + FastAPI (port 8000). Owns all model inference (YOLOv8, CLIP, PaddleOCR, Gemini for report text).

Shared TypeScript types live in `shared/` (e.g. `shared/types.ts`) and are imported by both frontend and backend — keep enums (`JobStatus`, `VehicleType`, `DamageInfo`, etc.) in sync with `backend/src/db/schema.sql` when modifying.

## Request lifecycle (read this before changing the pipeline)

1. Frontend `POST /api/upload` → backend stores file in `backend/uploads/videos/`, inserts a `files` row and a `jobs` row (status `pending`), returns `jobId`.
2. Backend's `services/job_processor.ts` runs the job **in-process** (no queue). It POSTs the video path to ML service `/api/process` with retry/backoff (`isRetryableError` covers ECONNREFUSED/5xx; see `RETRY_CONFIG`).
3. ML service `src/api/process.py` runs the pipeline: `FrameExtractor` → `VehicleIdentifier` (CLIP) → `DashboardDetector`+`OdometerReader` (YOLO+PaddleOCR) → `DamageDetector` → `ExhaustClassifier` → `ReportGenerator` (Gemini). Models are loaded **once at startup** via `ModelRegistry` (singleton on `app.state`) — do not re-instantiate per request.
4. Backend writes results into the `inspections` table and flips the job to `completed`. Frontend polls `GET /api/jobs/:id` then fetches `GET /api/inspections/:id`.

Path crossing between services is awkward: ML service receives an absolute path and writes outputs under `backend/uploads/{frames,odometer_images}/`. `convert_to_relative_path` in `process.py` and `path_validator.py` convert between absolute disk paths and the relative paths the backend serves under `/uploads`.

## Static file access control

`backend/src/index.ts` mounts `/uploads` with a guard: only `/frames/` and `/odometer_images/` prefixes are served; raw `/videos/` is explicitly 403. If you add a new artifact directory, add it to `allowedPrefixes` there or it will be blocked.

## Common commands

Run all three services at once (recommended for local dev — handles port-clearing, venv creation, dep install):
```bash
./START_SERVICES.sh
```
Logs go to `/tmp/vi-{backend,ml-service,frontend}.log`. Ctrl+C kills all three.

Per-service:
```bash
# backend
cd backend && npm run dev          # tsx watch (port 3001)
cd backend && npm run build        # tsc → dist/
cd backend && npm run type-check   # tsc --noEmit
cd backend && npm run lint         # eslint src --ext .ts

# frontend
cd frontend && npm run dev         # next dev (port 3000)
cd frontend && npm run build
cd frontend && npm run lint
cd frontend && npm test            # jest (jsdom)
cd frontend && npx jest path/to/file.test.tsx   # single test

# ml-service
cd ml-service && source venv/bin/activate
python src/main.py                 # uvicorn (port 8000)
pytest tests/                      # full suite
pytest tests/integration/test_ml_pipeline.py::TestX::test_y    # single test
```

Docker: `docker-compose up` (dev) or `docker-compose -f docker-compose.prod.yml up` (prod).

## Testing notes

- **Frontend**: Jest + Testing Library, configured via `next/jest` in `frontend/jest.config.js`. Tests live in `frontend/__tests__/`.
- **ML service**: pytest. `tests/conftest.py` sets `SRC_DIR` on `sys.path`; tests in `tests/integration/` exercise the FastAPI app and pipeline.
- **Backend**: there are test files under `backend/src/__tests__/` (integration + e2e), **but `backend/package.json` has no `test` script and no Jest dependency** — these are spec scaffolds. Do not assume `npm test` works in backend; if you need to run them, you'll have to wire up Jest first.

## Conventions / gotchas

- The backend uses **synchronous** `better-sqlite3` — no `await` on DB calls. Schema is applied from `src/db/schema.sql` on init via `initDatabase()`.
- Job processing is in-process. CPU/GPU-heavy work happens in the ML service; backend just orchestrates and persists. Don't move ML logic into the backend.
- `ModelRegistry.initialize_all_models()` runs at FastAPI startup (`lifespan`). If startup fails, the service refuses to start by design — don't catch and continue.
- The frontend talks to the backend via `NEXT_PUBLIC_API_URL` (defaults to `http://localhost:3001/api`). The frontend never calls the ML service directly.
- Rate limit + helmet CSP are configured in `backend/src/index.ts`; CORS origins come from `config.cors.allowedOrigins` (env `CORS_ALLOWED_ORIGINS`).
- `JobStatus` and other enums in `shared/types.ts` must match the strings used in `schema.sql` comments and in `models/inspection.ts`.

## Environment variables

Backend (`.env`): `PORT`, `ML_SERVICE_URL`, `DATABASE_PATH`, `UPLOAD_MAX_SIZE`, `CORS_ALLOWED_ORIGINS`, `RATE_LIMIT_WINDOW_MS`, `RATE_LIMIT_MAX_REQUESTS`, `LOG_LEVEL`.
ML service (`.env`): `GEMINI_API_KEY` (optional; report text falls back without it), `PORT`, `LOG_LEVEL`, `CORS_ALLOWED_ORIGINS`.
Frontend (`.env.local`): `NEXT_PUBLIC_API_URL`.
