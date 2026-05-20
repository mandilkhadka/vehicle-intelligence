# Vehicle Intelligence Platform

**Language / 言語:** [English](#english) | [日本語](#japanese)

---

<a id="english"></a>

## What it does

Vehicle Intelligence ingests a 360° walkaround video of a vehicle and returns a
structured inspection report:

- **Identity** — vehicle type, brand, model, category, year, trim, evidence sources
- **Odometer** — reading from the dashboard (OCR + VLM chain)
- **Damage** — scratches, dents, rust, cracks, paint damage, broken lights, wheel
  damage, panel misalignment — each grounded to a body panel and tagged with an
  estimated repair cost and a per-detection rationale
- **Exhaust** — stock vs modified classifier
- **PDF report** — generated client-side from the inspection JSON

It also ships an **active-learning loop**: every damage detection can be
confirmed or rejected from the UI; reviewer feedback exports to a YOLO-format
training set with a single script.

## Architecture

Three services, each runnable on its own:

| Service | Stack | Port | Owns |
|---|---|---|---|
| `frontend/` | Next.js 16, React 19, Tailwind 4 | 3000 | UI, uploads, polling, PDF rendering, reviewer queue |
| `backend/` | Node, Express, TypeScript, SQLite (`better-sqlite3`) | 3001 | Persistence, upload pipeline, job orchestration, static file gating |
| `ml-service/` | Python, FastAPI | 8000 | All model inference — YOLOv8, CLIP, PaddleOCR, Gemini, OpenAI vision |

Shared TypeScript types live in `shared/types.ts`.

## Request lifecycle

1. Frontend optionally calls `POST /api/upload/preflight` to gate on blur,
   brightness, and vehicle presence before the user commits to a full upload.
2. `POST /api/upload` writes the video to `backend/uploads/videos/`, inserts a
   `files` row and a `jobs` row (status `pending`), returns `jobId`.
3. `services/job_processor.ts` runs the job **in-process** (no queue) and POSTs
   the absolute video path to ML `/api/process` with retry/backoff.
4. ML pipeline (`src/api/process.py`):
   `FrameExtractor` → `VehicleIdentifier` (CLIP) →
   `DashboardDetector` + `OdometerReader` (YOLO + PaddleOCR + VLM) →
   `DamageDetector` → `panel_inference.attach_parts_to_locations` →
   `repair_costs.estimate_repair_costs` →
   `damage_rationale.attach_rationales` (best-effort, batched VLM call) →
   `ExhaustClassifier` → `ReportGenerator`.
   Models load once at startup via `ModelRegistry`.
5. Backend persists the result into `inspections` and flips the job to
   `completed`. Frontend polls `GET /api/jobs/:id`, then fetches
   `GET /api/inspections/:id`.

A startup reaper plus a 5-minute interval reaper marks stuck jobs as failed so
the UI doesn't hang on rows nobody is processing. A 6-hour sweeper deletes raw
videos for completed jobs older than `VIDEO_RETENTION_DAYS`.

## Getting started

The fast path runs all three services with port-clearing, venv setup, and
dependency install handled:

```bash
./START_SERVICES.sh
```

Logs land in `/tmp/vi-{backend,ml-service,frontend}.log`. Ctrl+C kills all
three. Per-service commands below if you'd rather drive them yourself.

### Backend

```bash
cd backend
npm install
npm run dev          # tsx watch, port 3001
npm run build        # tsc → dist/
npm run type-check
npm run lint
```

### ML service

```bash
cd ml-service
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Vision LLM keys (both optional; the pipeline degrades gracefully).
# Either ml-service/.env or the repo-root .env is read.
export GEMINI_API_KEY=...
export OPENAI_API_KEY=...
export OPENAI_BASE_URL=http://localhost:11434/v1  # optional, OpenAI-compatible

python src/main.py   # uvicorn, port 8000
pytest tests/
```

### Frontend

```bash
cd frontend
npm install
npm run dev          # next dev, port 3000
npm run build
npm run lint
npm test             # jest (jsdom)
```

## Environment variables

Copy `.env.example` to `.env` at the repo root for Docker Compose.

| Service | Key | Default | Purpose |
|---|---|---|---|
| backend | `PORT` | 3001 | Server port |
| backend | `ML_SERVICE_URL` | `http://localhost:8000` | ML service base URL |
| backend | `DATABASE_PATH` | `./data/vehicle_intelligence.db` | SQLite file path |
| backend | `UPLOAD_MAX_SIZE` | `500MB` | Per-file upload limit |
| backend | `CORS_ALLOWED_ORIGINS` | `http://localhost:3000,http://localhost:3001` | Comma-separated |
| backend | `RATE_LIMIT_WINDOW_MS` / `RATE_LIMIT_MAX_REQUESTS` | 15min / 100 | Express rate limit |
| backend | `ML_SERVICE_TIMEOUT_MS` | 600000 | Outer ML axios timeout |
| backend | `VIDEO_RETENTION_DAYS` | 7 | Sweeper threshold |
| backend | `LOG_LEVEL` | `info` | pino level |
| ml-service | `GEMINI_API_KEY` | — | Primary VLM |
| ml-service | `OPENAI_API_KEY` | — | VLM fallback |
| ml-service | `OPENAI_BASE_URL` | OpenAI | OpenAI-compatible endpoint |
| ml-service | `ML_DEVICE` | auto | `cuda` / `mps` / `cpu` override |
| ml-service | `ML_STAGE_TIMEOUT_VEHICLE` / `_ODOMETER` / `_DAMAGE` / `_EXHAUST` / `_GEMINI` | — | Per-stage soft timeouts (seconds) |
| ml-service | `ML_DAMAGE_RATIONALE_TIMEOUT` | — | Cap on rationale VLM batch |
| frontend | `NEXT_PUBLIC_API_URL` | `http://localhost:3001/api` | Backend API |
| frontend | `BACKEND_URL` | `http://localhost:3001` | Where `/uploads/*` is proxied to |

## API surface

### Backend (`http://localhost:3001`)

**Inspection lifecycle**

- `POST /api/upload/preflight` — multipart video, returns blur/brightness/vehicle-presence diagnostics. Fails open on ML errors.
- `POST /api/upload` — multipart video (+ optional odometer image, identity fields). Returns `{ jobId, fileId }`.
- `GET /api/jobs/:id` — job status.
- `GET /api/inspections` — paginated list.
- `GET /api/inspections/:id` — full inspection.
- `PUT /api/inspections/:id/identity` — merge trusted identity evidence (VIN, registration, brand, model, year, variant).
- `PUT /api/inspections/:id/vlm` — merge externally generated VLM evidence.
- `POST /api/inspections/:id/retry-vlm` — rerun VLM from saved organized frames.

**Active-learning feedback**

- `POST /api/inspections/:id/feedback` — confirm / reject / wrong-type a detection.
- `GET  /api/inspections/:id/feedback` — list feedback for one inspection.
- `DELETE /api/inspections/:id/feedback/:fid` — remove one feedback row.
- `POST /api/inspections/:id/missing-damage` — reviewer-drawn bbox for a damage the model missed.
- `GET  /api/inspections/:id/missing-damage` / `DELETE …/:mid` — list / remove.
- `GET /api/feedback/export?since=ISO` — joined export of all feedback + missing-damage rows.
- `GET /api/feedback/review?limit=N` — uncertain detections (confidence closest to 0.5) for the reviewer queue.

**Other**

- `GET /api/metrics` — dashboard aggregates.
- `GET /health` — liveness.
- `/uploads/frames/*` and `/uploads/odometer_images/*` — guarded static serving. Raw `/uploads/videos/*` is **403** by design.

### ML service (`http://localhost:8000`)

- `POST /api/preflight` — sample 12 frames, return blur + brightness + vehicle-presence scores.
- `POST /api/process` — full inspection pipeline.
- `POST /api/retry-vlm` — VLM-only rerun from saved organized frames.
- `GET /health` — liveness.
- `GET /ready` — dependency readiness. Pass `?live_gemini=true&live_openai=true` to verify VLM quota/keys.

## Frontend pages

- `/` — inspection dashboard (volumes, confidence, recent inspections).
- `/inspect` — upload form. Runs pre-flight, then `POST /api/upload`.
- `/capture` — guided 8-stage walkaround recorder using `MediaRecorder` +
  `getUserMedia`. Samples brightness and blur every 500 ms; requires the
  `Permissions-Policy: camera=(self)` header in `next.config.js`.
- `/job/[id]` — job status polling with exponential backoff.
- `/inspection/[id]` — full report with part-grouped damage accordion, repair
  cost totals, per-snapshot 👍/👎 feedback, JSON + PDF download.
- `/review` — reviewer queue of the most-uncertain detections across all
  inspections.
- `/history` — paginated list of past inspections.

## Operational scripts

```bash
# Backend — export reviewer feedback as a YOLO-format training set.
cd backend
npx tsx scripts/export-training-set.ts --out ./training-set [--since 2026-01-01]
# Produces images/, labels/, classes.txt, manifest.json. Idempotent.

# ML — pipeline readiness and per-video completion audit.
cd ml-service
python scripts/check_pipeline_readiness.py --live-gemini --live-openai --json > /tmp/vip-readiness.json
python scripts/evaluate_video_understanding.py ../360.mov --with-models --read-odometer \
  --output-dir /tmp/vip-video-eval
python scripts/audit_pipeline_completion.py \
  --manifest /tmp/vip-video-eval/frame_analysis_manifest.json \
  --inspection-json /path/to/process_response.json \
  --readiness-json /tmp/vip-readiness.json

# ML — retry VLM step from saved organized frames after fixing quota.
python scripts/retry_vlm_analysis.py \
  --inspection-json /path/to/process_response_or_backend_inspection.json \
  --output-json /tmp/vip-vlm-retry.json \
  --merged-output-json /tmp/vip-process-response-with-vlm.json
```

## Conventions and gotchas

- The backend uses **synchronous** `better-sqlite3` — no `await` on DB calls.
- Job processing is **in-process**. Don't move ML work into the backend; don't
  rely on the backend keeping ML state across restarts.
- `ModelRegistry.initialize_all_models()` runs at FastAPI startup. If startup
  fails the service refuses to start — don't catch and continue.
- The frontend talks to the backend via `NEXT_PUBLIC_API_URL`. The frontend
  never calls the ML service directly. `/uploads/*` is proxied through Next's
  rewrites to keep `next/image` happy without remote whitelisting.
- `JobStatus` and other enums in `shared/types.ts` must match the strings used
  in `backend/src/db/schema.sql` and `models/inspection.ts`.
- Static file allow-list is in `backend/src/index.ts`. Adding a new output
  directory? Add its prefix to `allowedPrefixes` or it will be blocked.

## What this isn't (yet)

Honest list of production gaps:

- **No authentication.** Anyone with the URL can upload, read, and export.
- **In-process job orchestration** — no queue, no horizontal scale, restarts
  abandon running jobs (the reaper marks them as failed).
- **SQLite as the database** — single-writer, no replication, no PITR. Fine
  for an MVP, not for production.
- **No CI.** Test suites exist; nothing runs them on push.
- **Local-filesystem uploads** — won't survive a container restart or scale
  across replicas. Move to S3/GCS for production.
- **Multer MIME check only** — no magic-byte verification, no AV scan.

## Tech stack

**Frontend** — Next.js 16 (App Router, Turbopack), React 19, Tailwind 4,
shadcn/radix primitives, `@react-pdf/renderer`.

**Backend** — Node, Express, TypeScript, `better-sqlite3`, Zod, multer,
helmet, pino.

**ML service** — Python 3.10+, FastAPI, OpenCV, YOLOv8 (ultralytics), CLIP,
PaddleOCR, Tesseract, Google Gemini, OpenAI vision.

---

<a id="japanese"></a>

## 概要

このシステムは、車両の360度ウォークアラウンド動画を取り込み、構造化された検査レポートを返します。

- **識別** — 車種、ブランド、モデル、カテゴリ、年式、トリム、証拠の出所
- **走行距離** — ダッシュボードからの読み取り（OCR + VLM チェーン）
- **損傷** — 傷、へこみ、錆、ひび、塗装ダメージ、ライト破損、ホイール損傷、パネルずれ。検出ごとに車体パネルへ紐付け、推定修理費と根拠コメントを付与
- **排気** — 純正 / 改造の分類
- **PDF レポート** — 検査 JSON からクライアント側で生成

加えて **アクティブラーニングのループ** を備えます。UI 上で各損傷検出を確定/却下でき、レビュー結果は1コマンドで YOLO 形式の学習データとしてエクスポートできます。

## アーキテクチャ

3 サービス構成。それぞれ単独で起動可能です。

| サービス | スタック | ポート | 担当 |
|---|---|---|---|
| `frontend/` | Next.js 16, React 19, Tailwind 4 | 3000 | UI、アップロード、ポーリング、PDF 生成、レビュー画面 |
| `backend/` | Node, Express, TypeScript, SQLite | 3001 | 永続化、アップロード制御、ジョブ管理、静的ファイル制御 |
| `ml-service/` | Python, FastAPI | 8000 | YOLOv8, CLIP, PaddleOCR, Gemini, OpenAI ビジョンの推論 |

共有 TypeScript 型は `shared/types.ts`。

## リクエストの流れ

1. フロントエンドが任意で `POST /api/upload/preflight` を呼び、ぼかし・明るさ・車両検出の品質を事前判定。
2. `POST /api/upload` が動画を `backend/uploads/videos/` に保存し、`files` / `jobs` レコードを作成し `jobId` を返す。
3. `services/job_processor.ts` が **インプロセス** でジョブを実行し、絶対パスを ML `/api/process` に POST（リトライ/バックオフあり）。
4. ML パイプライン（`src/api/process.py`）:
   `FrameExtractor` → `VehicleIdentifier`（CLIP）→
   `DashboardDetector` + `OdometerReader`（YOLO + PaddleOCR + VLM）→
   `DamageDetector` → `panel_inference.attach_parts_to_locations` →
   `repair_costs.estimate_repair_costs` →
   `damage_rationale.attach_rationales`（バッチ VLM、ベストエフォート）→
   `ExhaustClassifier` → `ReportGenerator`。
   モデルは起動時に `ModelRegistry` で一度だけロード。
5. バックエンドが結果を `inspections` テーブルへ書き込み、ジョブを `completed` に更新。フロントは `GET /api/jobs/:id` → `GET /api/inspections/:id` の順でポーリング。

起動時と5分間隔の reaper がスタックしたジョブを `failed` 化。6時間ごとの sweeper が `VIDEO_RETENTION_DAYS` を超えた動画を削除します。

## はじめかた

3 サービスを一括起動（ポート空け、venv 作成、依存解決まで自動）:

```bash
./START_SERVICES.sh
```

ログは `/tmp/vi-{backend,ml-service,frontend}.log`。Ctrl+C で全停止。

個別の起動コマンドは英語版を参照してください（`npm run dev` / `python src/main.py` など）。

## 環境変数

主要な値は英語版の表を参照してください。Docker Compose を使う場合はリポジトリルートの `.env`（`.env.example` をコピー）を読み込みます。

## API

### バックエンド（`http://localhost:3001`）

検査ライフサイクル

- `POST /api/upload/preflight`、`POST /api/upload`、`GET /api/jobs/:id`、
- `GET /api/inspections`、`GET /api/inspections/:id`、
- `PUT /api/inspections/:id/identity`、`PUT /api/inspections/:id/vlm`、`POST /api/inspections/:id/retry-vlm`

アクティブラーニング

- `POST/GET/DELETE /api/inspections/:id/feedback`
- `POST/GET/DELETE /api/inspections/:id/missing-damage`
- `GET /api/feedback/export?since=ISO`、`GET /api/feedback/review?limit=N`

その他

- `GET /api/metrics`、`GET /health`、`/uploads/frames/*` と `/uploads/odometer_images/*`（`/uploads/videos/*` は 403）。

### ML サービス（`http://localhost:8000`）

- `POST /api/preflight`、`POST /api/process`、`POST /api/retry-vlm`、`GET /health`、`GET /ready`

## フロントエンドのページ

- `/` ダッシュボード
- `/inspect` アップロード（pre-flight 経由）
- `/capture` 8 ステージのガイド付き撮影（`MediaRecorder` + `getUserMedia`）
- `/job/[id]` ジョブステータス（指数バックオフのポーリング）
- `/inspection/[id]` レポート表示（パネル別損傷、推定修理費、👍/👎、JSON / PDF ダウンロード）
- `/review` 未確定検出のレビュー画面
- `/history` 過去の検査一覧

## 運用スクリプト

```bash
# レビュー結果を YOLO 学習データとして書き出し（冪等）
cd backend
npx tsx scripts/export-training-set.ts --out ./training-set [--since 2026-01-01]

# パイプライン readiness と動画ごとの完了監査
cd ml-service
python scripts/check_pipeline_readiness.py --live-gemini --live-openai --json > /tmp/vip-readiness.json
python scripts/evaluate_video_understanding.py ../360.mov --with-models --read-odometer \
  --output-dir /tmp/vip-video-eval
python scripts/audit_pipeline_completion.py \
  --manifest /tmp/vip-video-eval/frame_analysis_manifest.json \
  --inspection-json /path/to/process_response.json \
  --readiness-json /tmp/vip-readiness.json
```

## 現状の制約

- 認証なし。URL を知るだけでアップロード、閲覧、エクスポートが可能。
- ジョブはバックエンド内プロセスで実行。再起動すると進行中ジョブは reaper により失敗扱い。
- SQLite を使用。書き込みは単一、レプリケーションも PITR もなし。
- CI 未整備。テストは存在するが push 時に実行されない。
- アップロードはローカルファイルシステム保存。コンテナ再起動・水平スケールに耐えない（S3/GCS 推奨）。
- アップロードファイルの検証は multer の MIME チェックのみ。マジックバイト確認やウイルススキャンなし。
