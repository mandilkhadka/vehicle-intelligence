# Frontend

Next.js 16 (App Router, Turbopack) + React 19 + Tailwind 4 + shadcn-style
primitives. Runs on port 3000.

```bash
npm install
npm run dev          # next dev
npm run build
npm run start
npm run lint
npm test             # jest (jsdom)
npm run test:e2e     # playwright
```

## Environment

`.env.local`:

```env
NEXT_PUBLIC_API_URL=http://localhost:3001/api
BACKEND_URL=http://localhost:3001
```

`BACKEND_URL` is read at build time in `next.config.js` to set up the
`/uploads/*` rewrite — so `next/image` can use snapshot URLs without remote
host whitelisting.

## Pages

| Path | Purpose |
|---|---|
| `/` | Inspection dashboard. Stats cards, recent inspections, analytics. |
| `/inspect` | Upload form. Runs pre-flight, then `POST /api/upload`. |
| `/capture` | Guided 8-stage walkaround recorder using `MediaRecorder` + `getUserMedia`. Samples brightness and blur every 500 ms. |
| `/job/[id]` | Polls job status with exponential backoff (2 s → 30 s on consecutive failures). |
| `/inspection/[id]` | Full inspection report — identity, odometer, part-grouped damage, exhaust. JSON + PDF download. |
| `/review` | Reviewer queue: most-uncertain detections (`|conf − 0.5|`) across all inspections. |
| `/history` | Paginated list of past inspections. |

## Notable components

- `components/inspect/upload-dropzone.tsx` — drag-and-drop, runs pre-flight,
  surfaces blocked-upload UI with an "Upload anyway" escape hatch.
- `components/JobStatus.tsx` — exponential backoff polling, manual retry.
- `components/DamageInfo.tsx` — part-grouped accordion, total repair cost
  badge, confidence filter, per-snapshot 👍/👎 feedback.
- `components/InspectionPdfDocument.tsx` — multi-page A4 PDF with identity
  grid, damage summary, per-snapshot rationale + cost. Severity color-coded.
- `components/app-shell.tsx` — header + sidebar + main column.
- `components/page-header.tsx` — page title and description. The legacy
  `eyebrow` prop is accepted but no longer rendered.

## Talking to the backend

`lib/api.ts` exposes typed helpers — `runPreflight`, `submitDamageFeedback`,
`listDamageFeedback`, `submitMissingDamage`, `getReviewQueue`, `getMetrics`,
etc. The frontend never calls the ML service directly; the backend is the
only origin in CORS.

## Camera permissions

`/capture` needs `getUserMedia`. `next.config.js` sets

```
Permissions-Policy: camera=(self), microphone=(), geolocation=(), payment=()
```

so the browser will prompt on same-origin. A previous version of this file
shipped `camera=()` which silently blocked the prompt even after consent.

## Tests

Jest + Testing Library — `__tests__/` for components and pages. Playwright —
`e2e/full-pipeline.spec.ts` for full upload-to-report runs (requires all three
services up).
