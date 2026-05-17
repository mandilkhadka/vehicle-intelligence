# ML Service

Python FastAPI service for vehicle inspection processing.

## Setup

Requires Python 3.10+.

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables
# You can put these in ../.env or ml-service/.env; both are loaded.
export GEMINI_API_KEY=your_api_key_here  # Optional primary VLM
export OPENAI_API_KEY=your_api_key_here  # Optional VLM fallback
export OPENAI_BASE_URL=http://localhost:11434/v1  # Optional OpenAI-compatible local/internal endpoint
export OPENAI_VISION_MODEL=gpt-4.1-mini  # Optional, defaults to gpt-4.1-mini
export OPENAI_TEXT_MODEL=gpt-4.1-mini    # Optional report-generation fallback model
export ML_FRAME_EXTRACTION_FPS=2          # Optional, defaults to 2
export UPLOADS_ROOT=/app/uploads          # Optional shared upload/frame output directory for containers

# Run service
python3 src/main.py
```

## Services

- **FrameExtractor** - Extracts quality-filtered frames from video (2 per second by default)
- **VehicleFrameOrganizer** - Selects representative exterior angles, interior/dashboard shots, and odometer OCR crops
- **VehicleIdentifier** - Identifies vehicle type, brand, model, category, and candidate year/variant evidence
- **DashboardDetector** - Detects dashboard region
- **OdometerReader** - Reads odometer value using OCR
- **DamageDetector** - Detects scratches, dents, rust, cracks, and paint damage
- **ExhaustClassifier** - Classifies exhaust as stock or modified
- **ModificationDetector** - Uses CLIP prompt comparisons over organized frames for conservative multi-part stock/modified evidence
- **ReportGenerator** - Generates inspection report using Gemini/OpenAI VLM context when available

## API Endpoints

- `POST /api/process` - Process video
- `GET /health` - Health check
- `GET /ready` - Pipeline dependency readiness; add `?live_gemini=true&live_openai=true` to verify VLM keys/quotas

## Models

Models are downloaded automatically on first use:
- YOLOv8 (object detection)
- CLIP (vehicle identification)
- PaddleOCR (OCR)

## Video Understanding Evaluation

Run the frame extraction + organization stage against a local walkaround video
without starting the backend or frontend:

```bash
cd ml-service
python3 scripts/evaluate_video_understanding.py ../360.mov --output-dir /tmp/vip-video-eval
python3 scripts/evaluate_video_understanding.py ../360.mov --with-models \
  --read-odometer \
  --output-dir /tmp/vip-video-eval \
  --min-coverage 0.75 --min-high-confidence-coverage 0.5 \
  --min-dashboard-candidates 1 --min-odometer-confidence 0.5
python3 scripts/evaluate_video_understanding.py ../360.mov --read-odometer \
  --expected-json /path/to/annotations.json --min-odometer-confidence 0.5
python3 scripts/evaluate_video_understanding.py ../360.mov \
  --expected-json /path/to/annotations.json \
  --inspection-json /path/to/process_response.json \
  --require-visual-analysis
python3 scripts/check_pipeline_readiness.py
python3 scripts/check_pipeline_readiness.py --live-gemini
python3 scripts/check_pipeline_readiness.py --live-gemini --live-openai --json > /tmp/vip-readiness.json
python3 scripts/audit_pipeline_completion.py \
  --manifest /tmp/vip-video-eval/frame_analysis_manifest.json \
  --inspection-json /path/to/process_response.json \
  --readiness-json /tmp/vip-readiness.json
python3 scripts/retry_vlm_analysis.py \
  --inspection-json /path/to/process_response.json \
  --export-request-json /tmp/vip-external-vlm-request.json
python3 scripts/retry_vlm_analysis.py \
  --inspection-json /path/to/process_response.json \
  --output-json /tmp/vip-vlm-retry.json \
  --merged-output-json /tmp/vip-process-response-with-vlm.json \
  --vlm-result-json /path/to/external_vlm_result.json \
  --identity-override-json /path/to/trusted_identity.json
```

`POST /api/process` also accepts an optional `vehicle_identity_override` object
for trusted VIN, registration, or manually confirmed identity fields:

```json
{
  "vehicle_identity_override": {
    "source": "upload_form",
    "brand": "Toyota",
    "model": "Sienta",
    "year": "2024",
    "variant": "Hybrid Z",
    "type": "car",
    "vehicle_category": "compact minivan",
    "vin": "optional vin or chassis number",
    "registration": "optional registration"
  }
}
```

These fields are merged after video/VLM identification and are surfaced with
`identity_source`/`identity_override_fields` so exact year/trim can be verified
without forcing the video-only model to guess.

If Gemini/OpenAI is unavailable during the original process run, use
`scripts/retry_vlm_analysis.py` after fixing quota or API keys. It reloads the
saved organized representative frame package from a `/api/process` response or
backend inspection record and reruns only the VLM analysis step. Pass
`--merged-output-json` to also write a process-response-shaped JSON with the
fresh VLM result merged into
`gemini_analysis`, `report.visual_analysis`, and `vehicle_info`, so
`scripts/audit_pipeline_completion.py` can be rerun directly against the retry
artifact. The merged artifact drops the old embedded `report.pipeline_audit`
from the failed run; rerun the completion audit against the merged JSON to
produce fresh verification status. If trusted exact identity evidence arrives
after the original upload, pass `--identity-override-json` with fields such as
`year`, `variant`, `vin`, or `registration`; those fields are merged into
`vehicle_info` and `report.vehicle_details` with `identity_source` and
`identity_override_fields`. Add `--skip-vlm` when the only operation is merging
trusted identity evidence and Gemini/OpenAI should not be called. If another
tool already produced a compatible VLM result, pass it with `--vlm-result-json`
to merge it into the same auditable process-response artifact without calling a
provider. If no provider is available in the runtime, pass
`--export-request-json` to write the selected organized frame paths, metadata,
prompt, and expected response schema for an external VLM review; add
`--include-image-data` to embed the selected frames as base64 data URLs.
When auditing an artifact that contains imported external VLM evidence, keep the
merged JSON as evidence and pass `--no-require-live-vlm` to
`scripts/audit_pipeline_completion.py`; the default audit still requires the
current runtime to have a live Gemini/OpenAI/OpenAI-compatible VLM path.
For the running app, the backend `POST /api/inspections/:id/retry-vlm` route
calls the ML service `/api/retry-vlm` endpoint and merges the fresh VLM result
back into the inspection record.

Minimum external VLM result shape:

```json
{
  "available": true,
  "provider": "external_vlm_review",
  "vehicle": {
    "brand": "Toyota",
    "model": "Sienta",
    "year": "2024",
    "variant": "Hybrid Z",
    "type": "car",
    "vehicle_category": "compact minivan",
    "confidence": 0.92
  },
  "overall_condition": "good",
  "damage_items": [],
  "modification_items": []
}
```

The script writes `frame_analysis_manifest.json` with selected angle shots,
dashboard candidates, representative VLM frames, coverage metrics,
source-frame/timestamp metadata, `extraction_metadata`,
`frame_contact_sheet.jpg`, and
`annotation_template.json`. Add `--with-models` to load YOLO + CLIP for semantic
view scoring; without it, the organizer uses deterministic quality/dashboard
heuristics. Use
`--min-high-confidence-coverage` to override the high-confidence coverage gate;
model-backed runs default to requiring 0.5 high-confidence coverage, while
heuristic runs default to 0.0 so they can still generate annotation artifacts.
Fill the generated annotation template from the
contact sheet, then pass it back with `--expected-json` to measure view accuracy
against human-labeled frame ranges. Add an `odometer` value to the annotations
and pass `--read-odometer` to run OCR against the organized dashboard crops. OCR
requires PaddleOCR, a working `tesseract` binary, or a configured VLM fallback
for runtime processing. If no OCR/VLM path is available, the evaluator fails
the odometer gate explicitly instead of silently passing. By default,
`--read-odometer` also requires at least 0.5 confidence;
lower this with `--min-odometer-confidence` only when auditing noisy candidate
readings rather than accepting them as reliable. The annotation template also includes optional final inspection
expectations for vehicle identity, overall condition, damage items, and
modification items. The runtime pipeline also runs a local CLIP modification
scan for wheels, lights, body, paint/wrap, and interior evidence, while keeping
ambiguous categories as `unknown`. Pass a saved full ML `/api/process` response with
`--inspection-json` to validate those fields against the annotations. Add
`--require-visual-analysis` when auditing the full AI pipeline so the evaluator
fails if the saved response shows Gemini/VLM analysis was unavailable, for
example because of quota or billing limits. Use
`scripts/check_pipeline_readiness.py` before evaluating a new
machine: it reports whether frame extraction, model-backed angle scoring,
odometer reading, and VLM/report analysis are configured. Gemini is the primary
VLM path; `OPENAI_API_KEY` enables an OpenAI vision fallback for Gemini quota or
billing failures. The default check does not load large models or call paid
APIs; `--live-gemini` and `--live-openai` make one small request to each
configured provider and surface quota, billing-cap, or key failures.
Set `OPENAI_BASE_URL` to use an OpenAI-compatible local or internal endpoint;
when it is set, `OPENAI_API_KEY` can be omitted and the service will use a local
placeholder key for the OpenAI client. OpenAI-compatible calls use the Responses
API first and then fall back to Chat Completions for local servers that do not
implement Responses. Local ML commands and the FastAPI service load both
`ml-service/.env` and the repo root `.env`, so adding `OPENAI_API_KEY` to either
file is enough; Docker Compose reads the repo root `.env`.
Use `scripts/audit_pipeline_completion.py` as the final gate for a real video.
It maps the product requirements to concrete evidence and exits nonzero when
any required evidence is missing. The default gates require frame extraction,
CLIP/YOLO-backed organization, temporal sampling across at least 90% of the
source video, named view coverage for front/rear/sides/quarters plus interior
and dashboard, at least 75% overall angle coverage, at least 50%
high-confidence angle coverage, selected frame quality of at least 0.40,
dashboard/odometer candidates, odometer confidence of at least 0.50, a live
Gemini or OpenAI VLM path, exact maker/model/year/trim/type/category identity
with at least 0.70 confidence, the full damage schema
(`scratches`, `dents`, `rust`, `cracks`, `paint_damage`, `wheel_damage`,
`broken_lights`, `missing_parts`, `panel_misalignment`) with severity,
confidence-aware inspection section routing, stock versus modified evidence for
at least three concrete part categories from VLM, local CLIP, exhaust
classifier, VIN/registration data, or manual review, and an inspection summary.

`inspection_analysis` is the canonical post-processing artifact for UI
placement. It consumes organized frame evidence, local damage/exhaust results,
and Gemini/OpenAI-compatible VLM output, then emits stable sections such as
`front`, `dashboard`, `tyres`, `exhaust`, and `damage-closeups` with confidence,
quality, foreground box, timestamp, conflict-resolution, and rejected-frame
metadata. Keep new Gemini, OpenAI, Claude, or local VLM integrations behind the
provider boundary and return the same normalized schema so classification,
validation, audit, and frontend rendering remain separate from extraction and
provider-specific API details.

The audit intentionally fails closed. A local-only vehicle classifier can
produce useful candidates such as brand, model, year range, and variant
candidates, but exact year/trim acceptance requires live VLM evidence, VIN or
registration data, or manual confirmation. Likewise, an exhaust-only fallback is
not complete modification detection; complete status requires stock/modified
evidence for at least three visible part categories such as exhaust, wheels,
lights, paint/wrap, body, interior, or steering components. The local CLIP path
uses stricter thresholds for `modified` labels to avoid overclaiming when
zero-shot scores are ambiguous.

Recent real-video evaluator output for `../360.mov` with model-backed
organization produced 56 extracted frames, `clip_yolo_quality` organization,
1.0 angle coverage, 0.667 high-confidence coverage, 0.9745 temporal coverage,
all required exterior/dashboard views, three dashboard candidates, and local OCR
odometer `12292` at 0.759 confidence. After adding the local CLIP modification
scan, the refreshed process artifact passes the multi-part modification gate
with concrete stock evidence for exhaust, paint/wrap, and interior while keeping
ambiguous wheels/lights/body evidence as `unknown`. The stricter completion
audit still remains incomplete until a live VLM path is available and exact
year/trim is verified.

For annotated videos, pass `--expected-json` to score selected frames against
expected extracted-frame indices:

```json
{
  "views": {
    "front": [0, 3],
    "rear": { "min": 12, "max": 16 },
    "left": { "indices": [5, 6, 7] }
  },
  "dashboard": [24, 28],
  "inspection": {
    "vehicle": {
      "brand": "Toyota",
      "model": "Camry",
      "year": "2024",
      "variant": "Hybrid XLE",
      "type": "car"
    },
    "overall_condition": "good",
    "visual_analysis": { "available": true },
    "damage_items": [
      { "type": "paint_damage", "location": "front bumper", "severity": "moderate" }
    ],
    "modification_items": [
      { "part": "wheels", "status": "modified" }
    ]
  }
}
```

The evaluator includes `validation.view_accuracy` and dashboard-match results
in the manifest, and exits nonzero when `--min-view-accuracy` is not met or
when annotated odometer/inspection expectations do not match.

## Notes

- First run will download ML models (may take several minutes)
- GPU acceleration is optional but recommended for faster processing
- Gemini/OpenAI API keys are optional for local development, but a live VLM path is required for the completion audit and for accepting exact vehicle identity without manual review
