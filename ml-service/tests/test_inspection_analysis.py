from pathlib import Path
import sys

ML_SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(ML_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(ML_SERVICE_ROOT))

from src.services.inspection_analysis import InspectionAnalysisPipeline, canonical_section


class MockInspectionProvider:
    name = "mock_provider"

    def __init__(self):
        self.images = None
        self.frame_analysis = None

    async def analyze_inspection_images(self, images, frame_analysis):
        self.images = images
        self.frame_analysis = frame_analysis
        return {
            "available": True,
            "provider": self.name,
            "vehicle": {
                "brand": "Provider",
                "model": "Vision",
                "year": "2026",
                "vehicle_category": "sedan",
                "confidence": 0.88,
            },
            "per_frame": [
                {
                    "frame": images[0]["frame"],
                    "view": "dashboard",
                    "observations": "Dashboard instruments and infotainment are visible.",
                }
            ],
            "damage_items": [],
        }


def test_canonical_section_normalizes_required_labels():
    assert canonical_section("engine bay") == "engine-bay"
    assert canonical_section("tire") == "tyres"
    assert canonical_section("steering wheel") == "steering-wheel"
    assert canonical_section("damage close-up") == "damage-closeups"


def test_inspection_analysis_routes_sections_and_blocks_bad_dashboard_wheel_conflict():
    pipeline = InspectionAnalysisPipeline()
    result = _run(
        pipeline.analyze(
            frame_analysis={
                "angle_shots": {
                    "dashboard": {
                        "view": "dashboard",
                        "frame": "frames/test/organized/dashboard.jpg",
                        "preview_path": "frames/test/previews/dashboard.jpg",
                        "score": 0.86,
                        "quality_score": 0.92,
                        "vehicle_ratio": 0.0,
                        "dashboard_score": 0.9,
                        "high_confidence": True,
                    },
                    "wheels": {
                        "view": "wheels",
                        "frame": "frames/test/organized/wheel.jpg",
                        "score": 0.82,
                        "quality_score": 0.84,
                        "vehicle_ratio": 0.22,
                    },
                    "tyres": {
                        "view": "tyres",
                        "frame": "frames/test/organized/tyre.jpg",
                        "score": 0.8,
                        "quality_score": 0.82,
                        "vehicle_ratio": 0.21,
                    },
                    "exhaust": {
                        "view": "exhaust",
                        "frame": "frames/test/organized/exhaust.jpg",
                        "score": 0.77,
                        "quality_score": 0.8,
                        "vehicle_ratio": 0.18,
                    },
                },
                "dashboard_candidates": [],
                "representative_frames": [],
            },
            vehicle_info={"brand": "Toyota", "model": "Sienta", "year": "2024", "type": "car", "confidence": 0.9},
            damage={"locations": []},
            exhaust={"type": "stock", "confidence": 0.7},
            vlm_result={
                "available": True,
                "provider": "mock",
                "vehicle": {
                    "brand": "Toyota",
                    "model": "Sienta",
                    "year": "2024",
                    "type": "car",
                    "vehicle_category": "compact minivan",
                    "confidence": 0.95,
                },
                "per_frame": [
                    {
                        "frame": "frames/test/organized/dashboard.jpg",
                        "view": "wheel",
                        "observations": "Dashboard and steering wheel are visible.",
                    },
                    {
                        "frame": "frames/test/organized/wheel.jpg",
                        "view": "interior",
                        "observations": "Close view of wheel rim.",
                    },
                    {
                        "frame": "frames/test/organized/tyre.jpg",
                        "view": "seats",
                        "observations": "Tyre sidewall closeup.",
                    },
                    {
                        "frame": "frames/test/organized/exhaust.jpg",
                        "view": "exhaust",
                        "observations": "Rear lower tailpipe and exhaust tip.",
                    },
                ],
            },
        )
    )

    assert result["sections"]["dashboard"][0]["frame"].endswith("dashboard.jpg")
    assert result["sections"]["wheels"][0]["frame"].endswith("wheel.jpg")
    assert result["sections"]["tyres"][0]["frame"].endswith("tyre.jpg")
    assert result["sections"]["exhaust"][0]["frame"].endswith("exhaust.jpg")
    assert "dashboard_cannot_classify_as_wheel_or_tyre" in result["consistency"]["conflicts_resolved"]
    assert "tyres" in result["consistency"]["present_sections"]
    assert result["vehicle"]["manufacturer"] == "Toyota"
    assert result["vehicle"]["body_type"] == "compact minivan"


def test_inspection_analysis_rejects_background_heavy_low_quality_exterior():
    result = _run(
        InspectionAnalysisPipeline().analyze(
            frame_analysis={
                "angle_shots": {
                    "front": {
                        "view": "front",
                        "frame": "frames/test/organized/front.jpg",
                        "score": 0.7,
                        "quality_score": 0.2,
                        "vehicle_ratio": 0.0,
                    }
                },
                "dashboard_candidates": [],
                "representative_frames": [],
            },
            vehicle_info={},
            damage={},
            exhaust={},
            vlm_result={"available": False, "reason": "not configured"},
        )
    )

    assert result["sections"]["front"] == []
    assert result["rejected_images"][0]["section"] == "needs-review"
    assert set(result["rejected_images"][0]["rejected_reasons"]) == {"low_quality", "background_dominant"}


def test_inspection_analysis_merges_damage_detections_and_routes_damage_closeups():
    result = _run(
        InspectionAnalysisPipeline().analyze(
            frame_analysis={
                "angle_shots": {
                    "damage-closeups": {
                        "view": "damage-closeups",
                        "frame": "frames/test/organized/damage.jpg",
                        "score": 0.7,
                        "quality_score": 0.78,
                        "vehicle_ratio": 0.12,
                    }
                },
                "dashboard_candidates": [],
                "representative_frames": [],
            },
            vehicle_info={},
            damage={
                "severity": "medium",
                "locations": [
                    {
                        "type": "scratch",
                        "frame": "frames/test/organized/damage.jpg",
                        "linked_view": "damage-closeups",
                        "confidence": 0.82,
                        "bbox": [10, 20, 80, 90],
                    }
                ],
            },
            exhaust={},
            vlm_result={"available": False, "damage_items": []},
        )
    )

    assert result["sections"]["damage-closeups"][0]["frame"].endswith("damage.jpg")
    assert result["damage_detections"][0]["type"] == "scratch"
    assert result["damage_detections"][0]["bbox"] == [10, 20, 80, 90]
    assert result["stages"]["stage_5"]["damage_count"] == 1


def test_inspection_analysis_validates_odometer_and_exhaust_context():
    result = _run(
        InspectionAnalysisPipeline().analyze(
            frame_analysis={
                "angle_shots": {
                    "front": {
                        "view": "front",
                        "frame": "frames/test/organized/front.jpg",
                        "score": 0.74,
                        "quality_score": 0.81,
                        "vehicle_ratio": 0.32,
                    },
                    "rear": {
                        "view": "rear",
                        "frame": "frames/test/organized/rear.jpg",
                        "score": 0.72,
                        "quality_score": 0.8,
                        "vehicle_ratio": 0.28,
                    },
                },
                "dashboard_candidates": [],
                "representative_frames": [],
            },
            vehicle_info={},
            damage={},
            exhaust={},
            vlm_result={
                "available": True,
                "provider": "mock",
                "per_frame": [
                    {
                        "frame": "frames/test/organized/front.jpg",
                        "view": "odometer",
                        "observations": "Front bumper and grille are visible.",
                    },
                    {
                        "frame": "frames/test/organized/rear.jpg",
                        "view": "exhaust",
                        "observations": "Lower rear bumper and tailpipe are visible.",
                    },
                ],
            },
        )
    )

    assert result["sections"]["dashboard"][0]["frame"].endswith("front.jpg")
    assert result["sections"]["exhaust"][0]["frame"].endswith("rear.jpg")
    assert "odometer_requires_dashboard_or_interior_context" in result["consistency"]["conflicts_resolved"]


def test_inspection_analysis_rejects_exhaust_without_rear_or_direct_evidence():
    result = _run(
        InspectionAnalysisPipeline().analyze(
            frame_analysis={
                "angle_shots": {
                    "left": {
                        "view": "left",
                        "frame": "frames/test/organized/left.jpg",
                        "score": 0.7,
                        "quality_score": 0.78,
                        "vehicle_ratio": 0.3,
                    }
                },
                "dashboard_candidates": [],
                "representative_frames": [],
            },
            vehicle_info={},
            damage={},
            exhaust={},
            vlm_result={
                "available": True,
                "provider": "mock",
                "per_frame": [
                    {
                        "frame": "frames/test/organized/left.jpg",
                        "view": "exhaust",
                        "observations": "Left door and side panel are visible.",
                    }
                ],
            },
        )
    )

    assert result["sections"]["left"][0]["frame"].endswith("left.jpg")
    assert "exhaust_requires_lower_rear_or_direct_exhaust_evidence" in result["consistency"]["conflicts_resolved"]


def test_inspection_analysis_calls_provider_abstraction_when_vlm_result_is_unavailable():
    provider = MockInspectionProvider()
    result = _run(
        InspectionAnalysisPipeline(provider=provider).analyze(
            frame_analysis={
                "angle_shots": {
                    "dashboard": {
                        "view": "dashboard",
                        "frame": "frames/test/organized/dashboard.jpg",
                        "score": 0.8,
                        "quality_score": 0.83,
                        "dashboard_score": 0.9,
                        "high_confidence": True,
                    }
                },
                "dashboard_candidates": [],
                "representative_frames": [],
            },
            vehicle_info={},
            damage={},
            exhaust={},
            vlm_result={"available": False, "reason": "not configured"},
        )
    )

    assert provider.images[0]["expected_view"] == "dashboard"
    assert result["provider"] == "mock_provider"
    assert result["sections"]["dashboard"][0]["frame"].endswith("dashboard.jpg")
    assert result["vehicle"]["manufacturer"] == "Provider"


def _run(coro):
    import asyncio

    return asyncio.run(coro)
