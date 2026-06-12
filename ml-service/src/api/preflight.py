"""
Pre-flight quality gate.

Cheap, fast pass over a video before it enters the heavy inspection pipeline.
Decides whether the upload is usable at all (lighting, focus, vehicle in
frame, walkaround coverage) so we reject garbage early with clear feedback
instead of producing a degraded report.

Designed to complete in <8 seconds for a 30-second clip. No model
initialization here — reuses the YOLO model already loaded into
app.state.model_registry.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, List, Optional

import cv2
import numpy as np
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator

from src.services.model_registry import YOLO_INFERENCE_LOCK
from src.utils.path_validator import path_validator

logger = logging.getLogger(__name__)
router = APIRouter()


# Tunable thresholds. Defaults err on the side of acceptance — we want to
# block obvious failures (pitch black, totally blurry, no vehicle visible)
# without rejecting clips that the pipeline could rescue.
def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


PREFLIGHT_SAMPLE_FRAMES = _env_int("ML_PREFLIGHT_SAMPLE_FRAMES", 12)
PREFLIGHT_MIN_DURATION_SEC = _env_float("ML_PREFLIGHT_MIN_DURATION_SEC", 5.0)
PREFLIGHT_MAX_DURATION_SEC = _env_float("ML_PREFLIGHT_MAX_DURATION_SEC", 180.0)
PREFLIGHT_MIN_BRIGHTNESS = _env_float("ML_PREFLIGHT_MIN_BRIGHTNESS", 35.0)
PREFLIGHT_MAX_BRIGHTNESS = _env_float("ML_PREFLIGHT_MAX_BRIGHTNESS", 235.0)
PREFLIGHT_MIN_BLUR = _env_float("ML_PREFLIGHT_MIN_BLUR", 60.0)  # Laplacian variance
PREFLIGHT_MIN_VEHICLE_FRAMES = _env_float("ML_PREFLIGHT_MIN_VEHICLE_RATIO", 0.4)
PREFLIGHT_MIN_VEHICLE_AREA_RATIO = _env_float("ML_PREFLIGHT_MIN_VEHICLE_AREA_RATIO", 0.05)


class PreflightRequest(BaseModel):
    video_path: str = Field(..., description="Absolute path to the candidate video file")

    @field_validator("video_path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("video_path must not be empty")
        return value


class PreflightResponse(BaseModel):
    ok: bool
    can_proceed: bool
    duration_sec: Optional[float] = None
    sampled_frames: int = 0
    coverage_estimate: float = 0.0
    blur_score: Optional[float] = None
    brightness_score: Optional[float] = None
    vehicle_visible_ratio: float = 0.0
    issues: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    elapsed_sec: float = 0.0


def _sample_frame_indices(total: int, n: int) -> List[int]:
    if total <= 0 or n <= 0:
        return []
    if total <= n:
        return list(range(total))
    step = total / float(n)
    return [int(round(i * step)) for i in range(n)]


def _largest_vehicle_area(results) -> int:
    """COCO classes 2/3/7 are car/motorcycle/truck. Return largest bbox area."""
    best = 0
    for result in results or []:
        boxes = getattr(result, "boxes", None)
        if boxes is None:
            continue
        for box in boxes:
            try:
                class_id = int(box.cls[0])
            except Exception:
                continue
            if class_id not in (2, 3, 7):
                continue
            try:
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
            except Exception:
                continue
            area = max(0, int(x2) - int(x1)) * max(0, int(y2) - int(y1))
            if area > best:
                best = area
    return best


def _estimate_coverage(orientations: List[Optional[float]]) -> float:
    """
    Rough walkaround-coverage estimate from per-frame dominant orientations.
    We don't have device orientation server-side, so we proxy it from the
    YOLO bbox horizontal position drift — if the vehicle bbox centre stays
    in the same place the whole time, coverage is low; if it sweeps across
    the frame, coverage is high. Returns [0, 1].
    """
    xs = [x for x in orientations if x is not None]
    if len(xs) < 2:
        return 0.0
    spread = max(xs) - min(xs)
    # spread is normalized [0, 1]; values >= 0.6 = good sweep.
    return float(min(1.0, spread / 0.6))


@router.post("/preflight", response_model=PreflightResponse, status_code=status.HTTP_200_OK)
async def preflight(request: PreflightRequest, http_request: Request):
    """
    Run a fast quality check on a candidate video.

    Returns an actionable issue list. `can_proceed` is true only when no
    blocking issues are found; warnings are advisory and don't block.
    """
    # Security: keep path traversal protection consistent with /process.
    try:
        path_validator.validate_or_raise(request.video_path, "video")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    if not os.path.exists(request.video_path):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Video file not found: {request.video_path}",
        )

    model_registry = getattr(http_request.app.state, "model_registry", None)
    yolo = model_registry.get_yolo_model() if model_registry and model_registry.is_initialized else None

    # All the cv2 decoding + YOLO inference below is synchronous and can take
    # several seconds on CPU; run it in a worker thread so the event loop can
    # keep serving /health and concurrent requests. HTTPExceptions raised in
    # the helper propagate through the awaited thread unchanged.
    return await asyncio.to_thread(_preflight_sync, request.video_path, yolo)


def _preflight_sync(video_path: str, yolo: Any) -> PreflightResponse:
    """Synchronous body of the preflight check (runs in a worker thread)."""
    start = time.time()
    issues: List[str] = []
    warnings: List[str] = []

    capture = cv2.VideoCapture(video_path)
    if not capture.isOpened():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to open video file",
        )

    try:
        fps = capture.get(cv2.CAP_PROP_FPS) or 0.0
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        duration = (frame_count / fps) if fps > 0 else 0.0

        if frame_count <= 0 or width <= 0 or height <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Video file is empty or unreadable",
            )

        if duration > 0 and duration < PREFLIGHT_MIN_DURATION_SEC:
            issues.append(
                f"Clip is too short ({duration:.1f}s). Record at least "
                f"{int(PREFLIGHT_MIN_DURATION_SEC)} seconds with a full walkaround."
            )
        if duration > PREFLIGHT_MAX_DURATION_SEC:
            warnings.append(
                f"Clip is unusually long ({duration:.0f}s). Trim to under "
                f"{int(PREFLIGHT_MAX_DURATION_SEC)}s for faster processing."
            )

        sample_indices = _sample_frame_indices(frame_count, PREFLIGHT_SAMPLE_FRAMES)
        if not sample_indices:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Could not sample frames from video",
            )

        # Pull frames into memory (small set, OK).
        frames: List[np.ndarray] = []
        for idx in sample_indices:
            capture.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ok, frame = capture.read()
            if ok and frame is not None:
                frames.append(frame)

        if not frames:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to decode any frames from the video",
            )

        brightness_values: List[float] = []
        blur_values: List[float] = []
        vehicle_visible_count = 0
        bbox_centres_x: List[Optional[float]] = []

        # Batch YOLO across sampled frames in one call (much faster than per-frame).
        # The shared ultralytics instance is not thread-safe; hold the lock.
        batch_results: List[Any] = []
        if yolo is not None:
            try:
                with YOLO_INFERENCE_LOCK:
                    batch_results = list(yolo(frames))
            except Exception as exc:
                logger.warning("Preflight YOLO batch failed: %s", exc)
                batch_results = []

        frame_area = float(width) * float(height) if width and height else 1.0

        for i, frame in enumerate(frames):
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            brightness_values.append(float(np.mean(gray)))
            blur_values.append(float(cv2.Laplacian(gray, cv2.CV_64F).var()))

            if i < len(batch_results):
                vehicle_area = _largest_vehicle_area([batch_results[i]])
                if vehicle_area / max(frame_area, 1.0) >= PREFLIGHT_MIN_VEHICLE_AREA_RATIO:
                    vehicle_visible_count += 1

                    # Find bbox centre x normalized for coverage estimate.
                    boxes = getattr(batch_results[i], "boxes", None)
                    if boxes is not None:
                        best_cx: Optional[float] = None
                        best_area = 0
                        for box in boxes:
                            try:
                                cid = int(box.cls[0])
                            except Exception:
                                continue
                            if cid not in (2, 3, 7):
                                continue
                            try:
                                x1, _, x2, _ = box.xyxy[0].cpu().numpy()
                            except Exception:
                                continue
                            a = float(x2 - x1)
                            if a * a > best_area:
                                best_area = a * a
                                best_cx = (float(x1) + float(x2)) / 2.0 / max(width, 1)
                        bbox_centres_x.append(best_cx)
                    else:
                        bbox_centres_x.append(None)
                else:
                    bbox_centres_x.append(None)
            else:
                bbox_centres_x.append(None)

        sampled_count = len(frames)
        brightness_avg = float(np.mean(brightness_values)) if brightness_values else None
        blur_avg = float(np.mean(blur_values)) if blur_values else None
        vehicle_ratio = vehicle_visible_count / max(sampled_count, 1)
        coverage = _estimate_coverage(bbox_centres_x)

        if brightness_avg is not None and brightness_avg < PREFLIGHT_MIN_BRIGHTNESS:
            issues.append(
                "Video is too dark for reliable detection — record outdoors or "
                "under bright, even lighting."
            )
        elif brightness_avg is not None and brightness_avg > PREFLIGHT_MAX_BRIGHTNESS:
            warnings.append(
                "Video is overexposed — direct sun or glare may hide damage. "
                "Try shaded lighting."
            )

        if blur_avg is not None and blur_avg < PREFLIGHT_MIN_BLUR:
            issues.append(
                "Video is too blurry — slow down the walkaround and hold the "
                "camera steady."
            )

        if vehicle_ratio < PREFLIGHT_MIN_VEHICLE_FRAMES:
            issues.append(
                "No vehicle is clearly visible in most frames. Stand closer "
                "and keep the vehicle centred."
            )

        if coverage < 0.45 and not issues:
            warnings.append(
                "Walkaround coverage looks partial. Make a complete loop "
                "around the vehicle for the best report."
            )

        can_proceed = len(issues) == 0
        ok = can_proceed and not warnings

        return PreflightResponse(
            ok=ok,
            can_proceed=can_proceed,
            duration_sec=round(duration, 2) if duration else None,
            sampled_frames=sampled_count,
            coverage_estimate=round(coverage, 2),
            blur_score=round(blur_avg, 2) if blur_avg is not None else None,
            brightness_score=round(brightness_avg, 2) if brightness_avg is not None else None,
            vehicle_visible_ratio=round(vehicle_ratio, 2),
            issues=issues,
            warnings=warnings,
            elapsed_sec=round(time.time() - start, 2),
        )
    finally:
        capture.release()
