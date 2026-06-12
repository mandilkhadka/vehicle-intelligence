"""Regression tests for the preflight quality gate.

Covers two fixes:
- the heavy cv2/YOLO work was moved into _preflight_sync so the async endpoint
  can run it via asyncio.to_thread without blocking the event loop;
- the shared ultralytics YOLO instance is invoked under YOLO_INFERENCE_LOCK
  (ultralytics models are not safe for concurrent predict() calls).
"""

import cv2
import numpy as np

from src.api.preflight import PreflightResponse, _preflight_sync
from src.services import model_registry
from src.services.damage_detector import DamageDetector


def _write_video(path, frames=60, size=(64, 48), fps=10):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, size)
    assert writer.isOpened()
    for _ in range(frames):
        writer.write(np.full((size[1], size[0], 3), 200, dtype=np.uint8))
    writer.release()


class _LockAssertingYolo:
    def __init__(self):
        self.calls = 0

    def __call__(self, frames, **kwargs):
        assert model_registry.YOLO_INFERENCE_LOCK.locked(), (
            "shared YOLO inference must hold YOLO_INFERENCE_LOCK"
        )
        self.calls += 1
        return []


def test_preflight_sync_returns_response_and_holds_yolo_lock(tmp_path):
    video = tmp_path / "clip.mp4"
    _write_video(video)

    yolo = _LockAssertingYolo()
    response = _preflight_sync(str(video), yolo)

    assert isinstance(response, PreflightResponse)
    assert yolo.calls == 1
    assert response.sampled_frames > 0
    assert response.duration_sec is not None
    # Constant grey frames: no vehicle visible and zero sharpness — blocked.
    assert response.can_proceed is False
    assert response.issues


def test_preflight_sync_works_without_yolo(tmp_path):
    video = tmp_path / "clip.mp4"
    _write_video(video)

    response = _preflight_sync(str(video), None)

    assert isinstance(response, PreflightResponse)
    assert response.vehicle_visible_ratio == 0.0


def test_damage_detector_batch_vehicle_regions_holds_yolo_lock():
    yolo = _LockAssertingYolo()
    detector = DamageDetector(yolo_model=yolo, damage_model=None)

    regions = detector._batch_vehicle_regions(["/tmp/a.jpg", "/tmp/b.jpg"])

    assert yolo.calls == 1
    assert regions == {"/tmp/a.jpg": None, "/tmp/b.jpg": None}
