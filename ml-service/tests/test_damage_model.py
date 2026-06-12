"""Tests for the dedicated damage detection model service."""

import numpy as np
import pytest

from src.api.process import _dedupe_detector_vlm_overlaps
from src.services.damage_detector import DamageDetector
from src.services.damage_model import DamageDetectionModel, load_class_map


class _FakeBox:
    def __init__(self, class_id, confidence, xyxy):
        self.cls = np.array([class_id])
        self.conf = np.array([confidence])
        self.xyxy = np.array([xyxy], dtype=float)


class _FakeMasks:
    def __init__(self, polygons):
        self.xyn = polygons


class _FakeResult:
    def __init__(self, boxes, names, orig_shape=(720, 1280), masks=None):
        self.boxes = boxes
        self.names = names
        self.orig_shape = orig_shape
        self.masks = masks


class _FakeModel:
    """Mimics an ultralytics model: callable returning a list of Results."""

    def __init__(self, results):
        self._results = results
        self.names = results[0].names if results else {}

    def __call__(self, frame_paths, **kwargs):
        return self._results[: len(frame_paths)]


CARDD_NAMES = {0: "dent", 1: "scratch", 2: "crack", 3: "glass shatter", 4: "lamp broken", 5: "tire flat"}


def test_detect_maps_cardd_classes_and_emits_location_contract():
    result_obj = _FakeResult(
        boxes=[
            _FakeBox(1, 0.91, [100, 200, 300, 260]),   # scratch
            _FakeBox(3, 0.72, [400, 100, 600, 300]),   # glass shatter -> crack
            _FakeBox(4, 0.66, [50, 50, 120, 110]),     # lamp broken -> broken_light
            _FakeBox(5, 0.58, [700, 400, 900, 600]),   # tire flat -> wheel_damage
        ],
        names=CARDD_NAMES,
    )
    model = DamageDetectionModel(_FakeModel([result_obj]), model_name="cardd-test.pt")

    result = model.detect_sync(["/tmp/frame_front.jpg"])

    assert result["scratches"] == {"count": 1, "detected": True}
    assert result["cracks"] == {"count": 1, "detected": True}
    assert result["broken_lights"] == {"count": 1, "detected": True}
    assert result["wheel_damage"] == {"count": 1, "detected": True}
    assert result["total_count"] == 4
    assert result["detector"]["available"] is True
    assert result["detector"]["model"] == "cardd-test.pt"

    # Locations sorted by confidence, carrying the full contract.
    top = result["locations"][0]
    assert top["type"] == "scratch"
    assert top["source"] == "detector"
    assert top["frame"] == "/tmp/frame_front.jpg"
    assert top["bbox"] == [100, 200, 300, 260]
    assert top["frame_width"] == 1280
    assert top["frame_height"] == 720
    assert top["confidence"] == pytest.approx(0.91)
    assert top["severity"] in ("low", "medium", "high")


def test_detect_skips_unmapped_classes():
    result_obj = _FakeResult(
        boxes=[_FakeBox(0, 0.9, [10, 10, 100, 100])],
        names={0: "person"},
    )
    model = DamageDetectionModel(_FakeModel([result_obj]))

    result = model.detect_sync(["/tmp/frame.jpg"])

    assert result["locations"] == []
    assert result["total_count"] == 0
    assert result["severity"] == "low"


def test_detect_attaches_normalized_mask_polygons():
    polygon = np.array([[0.1, 0.2], [0.3, 0.2], [0.3, 0.4], [0.1, 0.4]])
    result_obj = _FakeResult(
        boxes=[_FakeBox(0, 0.8, [128, 144, 384, 288])],
        names=CARDD_NAMES,
        masks=_FakeMasks([polygon]),
    )
    model = DamageDetectionModel(_FakeModel([result_obj]))

    result = model.detect_sync(["/tmp/frame.jpg"])

    assert len(result["locations"]) == 1
    mask = result["locations"][0]["mask"]
    assert mask == [[0.1, 0.2], [0.3, 0.2], [0.3, 0.4], [0.1, 0.4]]


def test_class_map_env_override(monkeypatch):
    monkeypatch.setenv("ML_DAMAGE_CLASS_MAP", '{"Glass Shatter": "broken_light", "rust_spot": "rust"}')
    class_map = load_class_map()
    assert class_map["glass_shatter"] == "broken_light"
    assert class_map["rust_spot"] == "rust"
    assert class_map["scratch"] == "scratch"  # defaults preserved


def test_damage_detector_prefers_dedicated_model():
    result_obj = _FakeResult(boxes=[_FakeBox(1, 0.9, [10, 10, 200, 60])], names=CARDD_NAMES)
    damage_model = DamageDetectionModel(_FakeModel([result_obj]))
    detector = DamageDetector(yolo_model=object(), damage_model=damage_model)

    result = detector._detect_sync(["/tmp/frame.jpg"])

    assert result["scratches"]["count"] == 1
    assert result["locations"][0]["source"] == "detector"


def test_dedupe_drops_vlm_duplicates_of_detector_findings():
    damage_data = {
        "locations": [
            {
                "type": "scratch",
                "source": "detector",
                "linked_view": "front",
                "bbox": [100, 100, 300, 200],
                "frame_width": 1000,
                "frame_height": 800,
            },
            {  # same physical damage reported by the VLM — should be dropped
                "type": "scratch",
                "source": "vlm",
                "linked_view": "front",
                "bbox": [110, 95, 310, 210],
                "frame_width": 1000,
                "frame_height": 800,
            },
            {  # different view — kept
                "type": "scratch",
                "source": "vlm",
                "linked_view": "left",
                "bbox": [110, 95, 310, 210],
                "frame_width": 1000,
                "frame_height": 800,
            },
            {  # different type — kept
                "type": "dent",
                "source": "vlm",
                "linked_view": "front",
                "bbox": [105, 100, 305, 205],
                "frame_width": 1000,
                "frame_height": 800,
            },
        ]
    }

    _dedupe_detector_vlm_overlaps(damage_data)

    sources_and_views = [(loc["source"], loc.get("linked_view"), loc["type"]) for loc in damage_data["locations"]]
    assert ("vlm", "front", "scratch") not in sources_and_views
    assert ("detector", "front", "scratch") in sources_and_views
    assert ("vlm", "left", "scratch") in sources_and_views
    assert ("vlm", "front", "dent") in sources_and_views


def test_dedupe_noop_without_detector_locations():
    damage_data = {
        "locations": [
            {"type": "scratch", "source": "vlm", "linked_view": "front", "bbox": [1, 1, 5, 5],
             "frame_width": 100, "frame_height": 100},
        ]
    }
    _dedupe_detector_vlm_overlaps(damage_data)
    assert len(damage_data["locations"]) == 1
