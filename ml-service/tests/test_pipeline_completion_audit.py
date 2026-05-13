import sys
from pathlib import Path

ML_SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(ML_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(ML_SERVICE_ROOT))

from scripts.audit_pipeline_completion import build_completion_audit  # noqa: E402


def _complete_manifest():
    return {
        "configuration": {"with_models": True},
        "summary": {
            "frames_extracted": 32,
            "organizer_method": "clip_yolo_quality",
            "coverage_ratio": 1.0,
            "high_confidence_coverage_ratio": 0.8,
            "missing_views": [],
            "low_confidence_views": ["right"],
            "dashboard_candidates": 2,
        },
        "odometer_ocr": {
            "value": 45230,
            "confidence": 0.91,
        },
        "frame_metadata": {
            "video_fps": 30.0,
            "total_source_frames": 300,
            "frames_extracted": 10,
            "frames": [
                {"extracted_index": 0, "timestamp_seconds": 0.0},
                {"extracted_index": 9, "timestamp_seconds": 9.5},
            ],
        },
        "angle_shots": {
            view: {
                "view": view,
                "frame_index": i,
                "organized_path": f"/tmp/{view}.jpg",
                "score": 0.8,
                "quality_score": 0.85,
            }
            for i, view in enumerate([
                "front",
                "front-left",
                "left",
                "rear-left",
                "rear",
                "rear-right",
                "right",
                "front-right",
                "interior",
                "dashboard",
            ])
        },
        "dashboard_candidates": [
            {
                "view": "dashboard",
                "frame_index": 12,
                "organized_path": "/tmp/dashboard_candidate.jpg",
                "quality_score": 0.82,
            }
        ],
    }


def _complete_inspection():
    return {
        "vehicle_info": {
            "brand": "Toyota",
            "model": "Camry",
            "year": "2024",
            "variant": "Hybrid XLE",
            "type": "car",
            "vehicle_category": "sedan",
            "confidence": 0.91,
            "identity_source": "registration",
            "identity_override_fields": ["year", "variant"],
            "registration": "sample-registration",
        },
        "gemini_analysis": {
            "available": True,
            "overall_condition": "good",
            "damage_items": [
                {"type": "paint_damage", "location": "front bumper", "severity": "moderate"},
            ],
            "modification_items": [
                {"part": "wheels", "status": "stock"},
                {"part": "exhaust", "status": "stock"},
                {"part": "lights", "status": "stock"},
            ],
        },
        "report": {
            "summary": "Inspection completed with minor cosmetic findings.",
        },
        "damage": {
            "scratches": {"count": 0, "detected": False},
            "dents": {"count": 0, "detected": False},
            "rust": {"count": 0, "detected": False},
            "cracks": {"count": 0, "detected": False},
            "paint_damage": {"count": 1, "detected": True},
            "severity": "medium",
            "locations": [
                {"type": "paint_damage", "location": "front bumper", "severity": "moderate"},
            ],
        },
    }


def test_completion_audit_passes_when_all_required_evidence_is_present():
    audit = build_completion_audit(
        manifest=_complete_manifest(),
        inspection=_complete_inspection(),
        readiness={"capabilities": {"llm_vlm_analysis": True}},
    )

    assert audit["passed"] is True
    assert audit["status"] == "complete"
    assert audit["missing"] == []
    vehicle_identity = next(item for item in audit["checks"] if item["id"] == "vehicle_identity")
    assert vehicle_identity["evidence"]["identity_source"] == "registration"
    assert vehicle_identity["evidence"]["identity_override_fields"] == ["year", "variant"]
    assert vehicle_identity["evidence"]["registration_supplied"] is True


def test_completion_audit_fails_closed_for_current_blockers():
    manifest = _complete_manifest()
    manifest["summary"]["high_confidence_coverage_ratio"] = 0.4
    manifest["odometer_ocr"] = {
        "value": 12192,
        "confidence": 0.42,
        "reason": "manual/VLM verification is required",
    }
    inspection = _complete_inspection()
    inspection["gemini_analysis"]["available"] = False
    inspection["gemini_analysis"]["reason"] = "Gemini API unavailable: billing cap exceeded"

    audit = build_completion_audit(
        manifest=manifest,
        inspection=inspection,
        readiness={"capabilities": {"llm_vlm_analysis": False}},
    )

    assert audit["passed"] is False
    assert audit["status"] == "incomplete"
    assert "high_confidence_angle_coverage" in audit["missing"]
    assert "odometer_verified" in audit["missing"]
    assert "vlm_available" in audit["missing"]
    assert "named_view_coverage" not in audit["missing"]
    assert "condition_assessment" not in audit["missing"]
    assert "damage_detection" not in audit["missing"]
    assert "modification_detection" not in audit["missing"]


def test_completion_audit_reports_missing_artifacts():
    audit = build_completion_audit()

    assert audit["passed"] is False
    assert "frame_extraction" in audit["missing"]
    assert "full_video_temporal_coverage" in audit["missing"]
    assert "named_view_coverage" in audit["missing"]
    assert "vehicle_identity" in audit["missing"]
    assert "condition_assessment" in audit["missing"]
    assert "damage_detection" in audit["missing"]
    assert "modification_detection" in audit["missing"]
    assert "inspection_summary" in audit["missing"]


def test_completion_audit_requires_all_requested_damage_categories():
    inspection = _complete_inspection()
    del inspection["damage"]["cracks"]
    del inspection["damage"]["paint_damage"]

    audit = build_completion_audit(
        manifest=_complete_manifest(),
        inspection=inspection,
        readiness={"capabilities": {"llm_vlm_analysis": True}},
    )
    damage_check = next(item for item in audit["checks"] if item["id"] == "damage_detection")

    assert audit["passed"] is False
    assert "damage_detection" in audit["missing"]
    assert damage_check["evidence"]["missing_categories"] == ["cracks", "paint_damage"]


def test_completion_audit_requires_each_named_walkaround_view():
    manifest = _complete_manifest()
    del manifest["angle_shots"]["interior"]
    del manifest["angle_shots"]["rear-right"]

    audit = build_completion_audit(
        manifest=manifest,
        inspection=_complete_inspection(),
        readiness={"capabilities": {"llm_vlm_analysis": True}},
    )
    view_check = next(item for item in audit["checks"] if item["id"] == "named_view_coverage")

    assert audit["passed"] is False
    assert "named_view_coverage" in audit["missing"]
    assert view_check["evidence"]["missing_named_views"] == ["rear-right", "interior"]


def test_completion_audit_requires_temporal_coverage_across_video():
    manifest = _complete_manifest()
    manifest["frame_metadata"]["frames"][-1]["timestamp_seconds"] = 4.0

    audit = build_completion_audit(
        manifest=manifest,
        inspection=_complete_inspection(),
        readiness={"capabilities": {"llm_vlm_analysis": True}},
    )
    temporal_check = next(item for item in audit["checks"] if item["id"] == "full_video_temporal_coverage")

    assert audit["passed"] is False
    assert "full_video_temporal_coverage" in audit["missing"]
    assert temporal_check["evidence"]["temporal_coverage_ratio"] == 0.4


def test_completion_audit_requires_selected_frame_quality_metadata():
    manifest = _complete_manifest()
    manifest["angle_shots"]["front"]["quality_score"] = 0.2
    del manifest["angle_shots"]["rear"]["organized_path"]

    audit = build_completion_audit(
        manifest=manifest,
        inspection=_complete_inspection(),
        readiness={"capabilities": {"llm_vlm_analysis": True}},
    )
    quality_check = next(item for item in audit["checks"] if item["id"] == "selected_frame_quality")

    assert audit["passed"] is False
    assert "selected_frame_quality" in audit["missing"]
    assert quality_check["evidence"]["missing_paths"] == ["rear"]
    assert quality_check["evidence"]["low_quality"] == [{"view": "front", "quality_score": 0.2}]


def test_completion_audit_requires_concrete_modification_status():
    inspection = _complete_inspection()
    inspection["gemini_analysis"]["modification_items"] = [
        {"part": "wheels", "status": "unknown"},
    ]

    audit = build_completion_audit(
        manifest=_complete_manifest(),
        inspection=inspection,
        readiness={"capabilities": {"llm_vlm_analysis": True}},
    )

    assert audit["passed"] is False
    assert "modification_detection" in audit["missing"]


def test_completion_audit_rejects_exhaust_only_modification_fallback():
    inspection = _complete_inspection()
    inspection["gemini_analysis"]["modification_items"] = []
    inspection["report"]["modification_assessment"] = {
        "items": [
            {"part": "exhaust", "status": "stock"},
        ],
    }

    audit = build_completion_audit(
        manifest=_complete_manifest(),
        inspection=inspection,
        readiness={"capabilities": {"llm_vlm_analysis": True}},
    )
    modification = next(item for item in audit["checks"] if item["id"] == "modification_detection")

    assert audit["passed"] is False
    assert "modification_detection" in audit["missing"]
    assert modification["evidence"]["exhaust_only"] is True


def test_completion_audit_requires_vehicle_identity_confidence():
    inspection = _complete_inspection()
    inspection["vehicle_info"]["confidence"] = 0.36

    audit = build_completion_audit(
        manifest=_complete_manifest(),
        inspection=inspection,
        readiness={"capabilities": {"llm_vlm_analysis": True}},
    )

    assert audit["passed"] is False
    assert "vehicle_identity" in audit["missing"]


def test_completion_audit_requires_vehicle_trim_and_category():
    inspection = _complete_inspection()
    inspection["vehicle_info"]["variant"] = None
    inspection["vehicle_info"]["vehicle_category"] = None
    inspection["vehicle_info"]["year_range"] = "2022-present"
    inspection["vehicle_info"]["variant_candidates"] = ["Hybrid", "Z", "G", "X"]

    audit = build_completion_audit(
        manifest=_complete_manifest(),
        inspection=inspection,
        readiness={"capabilities": {"llm_vlm_analysis": True}},
    )

    identity = next(item for item in audit["checks"] if item["id"] == "vehicle_identity")

    assert audit["passed"] is False
    assert "vehicle_identity" in audit["missing"]
    assert identity["evidence"]["variant"] is None
    assert identity["evidence"]["vehicle_category"] is None
    assert identity["evidence"]["year_range"] == "2022-present"
    assert identity["evidence"]["variant_candidates"] == ["Hybrid", "Z", "G", "X"]
