# Backend

Express + TypeScript + `better-sqlite3` (synchronous). Owns persistence, the
upload pipeline, and orchestrates calls to the ML service. Runs on port 3001.

```bash
npm install
npm run dev          # tsx watch
npm run build        # tsc → dist/
npm run start        # node dist/index.js
npm run type-check
npm run lint
```

Test files exist under `src/__tests__/` but `package.json` has no `test`
script and no Jest dependency — they're specs, not a working suite. Wire up
Jest before running.

## Environment

```env
PORT=3001
ML_SERVICE_URL=http://localhost:8000
ML_SERVICE_TIMEOUT_MS=600000
DATABASE_PATH=./data/vehicle_intelligence.db
UPLOAD_MAX_SIZE=500MB
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://localhost:3001
RATE_LIMIT_WINDOW_MS=900000
RATE_LIMIT_MAX_REQUESTS=100
VIDEO_RETENTION_DAYS=7
LOG_LEVEL=info
```

## API routes

All under `/api` unless noted.

### Upload pipeline

| Method | Path | Notes |
|---|---|---|
| `POST` | `/api/upload/preflight` | Multipart `video`. Forwards to ML `/api/preflight`, then deletes the temp file. Fails open on ML errors. |
| `POST` | `/api/upload` | Multipart `video` (+ optional odometer image, identity fields). Creates `files` + `jobs` row, kicks off processing. |
| `GET`  | `/api/jobs/:id` | Job status. |

### Inspections

| Method | Path | Notes |
|---|---|---|
| `GET`  | `/api/inspections` | Paginated list. |
| `GET`  | `/api/inspections/:id` | Single inspection. |
| `PUT`  | `/api/inspections/:id/identity` | Merge trusted identity fields (VIN, registration, brand, etc.). Drops stale embedded audit so the inspection can be re-audited. |
| `PUT`  | `/api/inspections/:id/vlm` | Merge externally-generated VLM evidence. |
| `POST` | `/api/inspections/:id/retry-vlm` | Rerun the VLM step from saved organized frames. |

### Active-learning feedback

| Method | Path | Notes |
|---|---|---|
| `POST`   | `/api/inspections/:id/feedback` | Body: `{ location_index, verdict, corrected_type?, corrected_severity?, note?, reviewer? }`. Verdicts: `confirmed` \| `false_positive` \| `wrong_type`. |
| `GET`    | `/api/inspections/:id/feedback` | List feedback for one inspection. |
| `DELETE` | `/api/inspections/:id/feedback/:fid` | Remove one row. |
| `POST`   | `/api/inspections/:id/missing-damage` | Reviewer-drawn bbox for a damage the model missed. |
| `GET`    | `/api/inspections/:id/missing-damage` | List. |
| `DELETE` | `/api/inspections/:id/missing-damage/:mid` | Remove. |
| `GET`    | `/api/feedback/export?since=ISO` | Joined dump of both tables with `damage_summary`. |
| `GET`    | `/api/feedback/review?limit=N` | Detections with confidence closest to 0.5, across all inspections, that have no feedback yet. |

### Other

| Method | Path | Notes |
|---|---|---|
| `GET` | `/api/metrics` | Dashboard aggregates. |
| `GET` | `/health` | Liveness. |

## Static file access control

`src/index.ts` mounts `/uploads` with a prefix guard:

- `/uploads/frames/*` — served.
- `/uploads/odometer_images/*` — served.
- Everything else under `/uploads/` — **403**. Including raw videos.

If you add a new artifact directory, add its prefix to `allowedPrefixes` in
`index.ts` or it will be blocked.

## Background jobs

Set up in `src/index.ts`:

- **Startup reaper** — `reapStuckJobs()` on boot.
- **5-minute interval reaper** — marks jobs as failed if they've been
  `processing` past `STUCK_PROCESSING_MAX_MINUTES`, or `pending` past
  `STUCK_PENDING_MAX_MINUTES`.
- **6-hour video sweeper** — deletes raw videos for completed jobs older than
  `VIDEO_RETENTION_DAYS`.

These exist because job processing is **in-process**. A backend restart
abandons running jobs; the reaper picks up the pieces on next boot.

## Database

SQLite via `better-sqlite3`. WAL mode. Schema is applied from
`src/db/schema.sql` on init via `initDatabase()`. Newer tables
(`damage_feedback`, `damage_missing_reports`) are applied as `CREATE TABLE IF
NOT EXISTS` migrations in `src/db/init.ts`.

There is **no migration tooling** beyond `IF NOT EXISTS`. Altering an existing
column requires a manual data migration.

## Uploads on disk

```
uploads/
├── videos/            raw uploads (not served publicly)
├── frames/            extracted frames (served at /uploads/frames/)
├── odometer_images/   optional user-supplied odometer photos
└── preflight/         transient — deleted after each preflight call
```

## Scripts

```bash
# Export reviewer feedback into a YOLO-format training set.
# Idempotent: prior rows tracked in manifest.json are skipped.
npx tsx scripts/export-training-set.ts --out ./training-set [--since 2026-01-01] [--verbose]
# Produces:
#   <out>/images/<file>.jpg     — copy of source frame
#   <out>/labels/<file>.txt     — YOLO: <class_id> <cx> <cy> <w> <h>
#   <out>/classes.txt           — ordered class list
#   <out>/manifest.json         — provenance
```

## Dependencies of note

- `helmet` + `cors` + `express-rate-limit` — security baseline
- `multer` — uploads (MIME check only; no magic-byte or AV scan)
- `pino` / `pino-http` — structured logs
- `zod` — request/response validation; ML response is Zod-parsed before persist
