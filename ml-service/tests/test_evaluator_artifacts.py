import json
import sys
from pathlib import Path

import cv2
import numpy as np

ML_SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(ML_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(ML_SERVICE_ROOT))

from scripts.evaluate_video_understanding import (  # noqa: E402
    _compact_item,
    _dashboard_paths_from_frame_analysis,
    _effective_high_confidence_threshold,
    _expected_has_odometer,
    _extract_odometer,
    _extract_visual_analysis,
    _markers_by_frame_index,
    _exit_code,
    _selection_matches,
    _validate_against_expected,
    _validate_inspection,
    _validate_odometer,
    _write_annotation_template,
    _write_contact_sheet,
)


def _write_image(path: Path, value: int) -> str:
    image = np.full((80, 120, 3), value, dtype=np.uint8)
    cv2.imwrite(str(path), image)
    return str(path)


def test_evaluator_preserves_and_prefers_odometer_readout_crop(temp_dir):
    raw = Path(_write_image(temp_dir / "raw.jpg", 30))
    crop = Path(_write_image(temp_dir / "crop.jpg", 80))
    readout = Path(_write_image(temp_dir / "readout.jpg", 180))
    organized = Path(_write_image(temp_dir / "organized.jpg", 120))
    frame_analysis = {
        "dashboard_candidates": [
            {
                "frame": str(raw),
                "organized_path": str(organized),
                "crop_path": str(crop),
                "readout_crop_path": str(readout),
            }
        ],
    }

    assert _compact_item(frame_analysis["dashboard_candidates"][0])["readout_crop_path"] == str(readout)
    assert _dashboard_paths_from_frame_analysis(frame_analysis) == [str(readout)]


def test_annotation_artifacts_include_selected_indices(temp_dir):
    frames = [
        _write_image(temp_dir / "frame_0000.jpg", 80),
        _write_image(temp_dir / "frame_0001.jpg", 140),
        _write_image(temp_dir / "frame_0002.jpg", 200),
    ]
    manifest = {
        "output_dir": str(temp_dir),
        "angle_shots": {
            "front": {"frame_index": 0},
            "dashboard": {"frame_index": 2},
        },
        "dashboard_candidates": [
            {"frame_index": 2},
        ],
        "frame_metadata": {
            "frames": [
                {"extracted_index": 0, "source_frame_index": 0, "timestamp_seconds": 0.0},
                {"extracted_index": 1, "source_frame_index": 10, "timestamp_seconds": 1.0},
                {"extracted_index": 2, "source_frame_index": 20, "timestamp_seconds": 2.0},
            ]
        },
    }

    assert _markers_by_frame_index(manifest) == {
        0: ["front"],
        2: ["dashboard", "dash1"],
    }

    contact_sheet = temp_dir / "contact.jpg"
    annotation_template = temp_dir / "annotation_template.json"
    _write_contact_sheet(frames, manifest, contact_sheet, thumb_width=100, columns=2)
    _write_annotation_template(frames, manifest, annotation_template)

    assert contact_sheet.exists()
    assert cv2.imread(str(contact_sheet)) is not None

    template = json.loads(annotation_template.read_text(encoding="utf-8"))
    assert template["_frames_extracted"] == 3
    assert template["_frame_metadata"][2]["timestamp_seconds"] == 2.0
    assert template["_selected_indices"]["front"] == 0
    assert template["_dashboard_candidate_indices"] == [2]
    assert "front" in template["views"]
    assert "odometer" in template["views"]
    assert template["dashboard"] == {"indices": []}
    assert template["odometer"] == {"value": None, "tolerance": 0}
    assert template["inspection"]["vehicle"]["brand"] is None
    assert template["inspection"]["overall_condition"] is None
    assert template["inspection"]["visual_analysis"] == {"available": None}
    assert template["inspection"]["damage_items"][0]["severity"] is None
    assert template["inspection"]["modification_items"][0]["status"] is None


def test_odometer_expected_detection_and_validation():
    assert _expected_has_odometer({"odometer": {"value": 123456}}) is True
    assert _expected_has_odometer({"odometer": 123456}) is True
    assert _expected_has_odometer({"odometer": {"value": None}}) is False
    assert _expected_has_odometer({}) is False

    assert _validate_odometer({"value": 123458}, {"value": 123456, "tolerance": 3}) == {
        "expected": 123456,
        "actual": 123458,
        "tolerance": 3,
        "matched": True,
    }
    assert _validate_odometer({"value": 123500}, {"value": 123456, "tolerance": 3})["matched"] is False
    assert _validate_odometer({"value": None}, 123456)["matched"] is False
    assert _validate_odometer({"value": 123456}, {"value": None}) is None


def test_selection_matching_supports_source_frames_and_timestamps():
    selected = {
        "frame_index": 7,
        "extracted_index": 7,
        "source_frame_index": 210,
        "timestamp_seconds": 3.54,
    }

    assert _selection_matches(selected, {"source_frame_index": [200, 220]}) is True
    assert _selection_matches(selected, {"source_frame_indices": [210, 240]}) is True
    assert _selection_matches(
        selected,
        {"timestamp_seconds": {"value": 3.5, "tolerance_seconds": 0.1}},
    ) is True
    assert _selection_matches(
        selected,
        {"extracted_index": 7, "source_frame_index": [200, 220]},
    ) is True
    assert _selection_matches(selected, {"timestamp_seconds": {"min": 4.0, "max": 5.0}}) is False


def test_exit_code_fails_when_requested_odometer_has_no_value():
    class Args:
        min_coverage = 0.75
        min_high_confidence_coverage = 0.0
        min_dashboard_candidates = 1
        min_view_accuracy = 0.8
        read_odometer = True
        min_odometer_confidence = 0.1

    manifest = {
        "summary": {
            "coverage_ratio": 1.0,
            "high_confidence_coverage_ratio": 1.0,
            "dashboard_candidates": 1,
            "frames_extracted": 4,
        },
        "odometer_ocr": {
            "attempted": True,
            "available": False,
            "value": None,
            "confidence": 0.0,
            "reason": "no odometer value returned",
        },
    }

    assert _exit_code(manifest, Args()) == 2


def test_exit_code_fails_when_requested_odometer_confidence_is_low():
    class Args:
        min_coverage = 0.75
        min_high_confidence_coverage = 0.0
        min_dashboard_candidates = 1
        min_view_accuracy = 0.8
        read_odometer = True
        min_odometer_confidence = 0.5

    manifest = {
        "summary": {
            "coverage_ratio": 1.0,
            "high_confidence_coverage_ratio": 1.0,
            "dashboard_candidates": 1,
            "frames_extracted": 4,
        },
        "odometer_ocr": {
            "attempted": True,
            "available": True,
            "value": 112028,
            "confidence": 0.42,
        },
    }

    assert _exit_code(manifest, Args()) == 2


def test_high_confidence_threshold_defaults_only_for_model_backed_runs():
    class ModelArgs:
        min_high_confidence_coverage = None
        with_models = True

    class HeuristicArgs:
        min_high_confidence_coverage = None
        with_models = False

    assert _effective_high_confidence_threshold(ModelArgs()) == 0.5
    assert _effective_high_confidence_threshold(HeuristicArgs()) == 0.0


def test_inspection_expected_validation_matches_vehicle_damage_and_modifications(temp_dir):
    expected = {
        "inspection": {
            "vehicle": {
                "brand": "Toyota",
                "model": "Camry",
                "year": "2024",
                "variant": "Hybrid XLE",
                "type": "car",
            },
            "overall_condition": "good",
            "odometer": {
                "value": 45230,
                "tolerance": 5,
            },
            "damage_items": [
                {
                    "type": "paint_damage",
                    "location": "front bumper",
                    "severity": "moderate",
                }
            ],
            "modification_items": [
                {
                    "part": "wheels",
                    "status": "modified",
                }
            ],
        }
    }
    payload = {
        "vehicle_info": {
            "brand": "Toyota",
            "model": "Camry",
            "year": "2024",
            "variant": "Hybrid XLE",
            "type": "car",
            "confidence": 0.93,
        },
        "gemini_analysis": {
            "overall_condition": "Good",
            "damage_items": [
                {
                    "type": "paint_damage",
                    "location": "front bumper",
                    "severity": "medium",
                }
            ],
            "modification_items": [
                {
                    "part": "wheels",
                    "status": "modified",
                }
            ],
        },
        "odometer": {
            "value": 45231,
            "confidence": 0.91,
        },
    }

    result = _validate_inspection(payload, expected)

    assert result["matched"] is True
    assert result["vehicle"]["matched_fields"] == 5
    assert result["odometer"]["matched"] is True
    assert result["damage_items"]["matched_items"] == 1
    assert result["modification_items"]["matched_items"] == 1


def test_extract_odometer_supports_backend_discrete_and_json_shapes():
    assert _extract_odometer({"odometer_info": {"value": 123456, "confidence": 0.8}}) == {
        "value": 123456,
        "confidence": 0.8,
    }
    assert _extract_odometer({
        "odometer_value": 123456,
        "odometer_confidence": 0.7,
        "speedometer_image_path": "frames/odometer.jpg",
    }) == {
        "value": 123456,
        "confidence": 0.7,
        "speedometer_image_path": "frames/odometer.jpg",
    }


def test_extract_visual_analysis_supports_process_and_report_shapes():
    assert _extract_visual_analysis({
        "gemini_analysis": {
            "available": True,
        },
    }) == {
        "available": True,
        "reason": None,
        "source": "gemini_analysis",
    }
    assert _extract_visual_analysis({
        "report": {
            "visual_analysis": {
                "available": False,
                "reason": "Gemini API unavailable: quota exceeded",
            },
        },
    }) == {
        "available": False,
        "reason": "Gemini API unavailable: quota exceeded",
        "source": "report.visual_analysis",
    }


def test_inspection_expected_validation_can_require_visual_analysis():
    expected = {
        "inspection": {
            "visual_analysis": {
                "available": True,
            },
        }
    }
    payload = {
        "gemini_analysis": {
            "available": False,
            "reason": "Gemini API unavailable: billing cap exceeded",
        },
    }

    result = _validate_inspection(payload, expected)

    assert result["matched"] is False
    assert result["visual_analysis"] == {
        "expected_available": True,
        "actual_available": False,
        "reason": "Gemini API unavailable: billing cap exceeded",
        "source": "gemini_analysis",
        "matched": False,
    }


def test_expected_validation_fails_when_inspection_payload_is_missing(temp_dir):
    expected = {
        "inspection": {
            "vehicle": {"brand": "Toyota"},
            "overall_condition": "good",
            "odometer": {"value": 123456},
        }
    }
    expected_path = temp_dir / "annotations.json"
    expected_path.write_text(json.dumps(expected), encoding="utf-8")

    result = _validate_against_expected(
        frame_analysis={"angle_shots": {}, "dashboard_candidates": []},
        expected_path=expected_path,
        expected=expected,
        odometer_ocr=None,
        inspection_payload=None,
    )

    assert result["inspection"]["actual_available"] is False
    assert result["inspection"]["matched"] is False


def test_expected_validation_reports_source_frame_and_timestamp_matches(temp_dir):
    expected = {
        "views": {
            "front": {"source_frame_index": [200, 220]},
        },
        "dashboard": {
            "timestamp_seconds": {"value": 10.5, "tolerance_seconds": 0.25},
        },
    }
    expected_path = temp_dir / "annotations.json"
    expected_path.write_text(json.dumps(expected), encoding="utf-8")

    result = _validate_against_expected(
        frame_analysis={
            "angle_shots": {
                "front": {
                    "frame_index": 7,
                    "extracted_index": 7,
                    "source_frame_index": 210,
                    "timestamp_seconds": 3.5,
                    "frame": "front.jpg",
                },
            },
            "dashboard_candidates": [
                {
                    "frame_index": 21,
                    "extracted_index": 21,
                    "source_frame_index": 630,
                    "timestamp_seconds": 10.52,
                    "crop_path": "dashboard_crop.jpg",
                },
            ],
        },
        expected_path=expected_path,
        expected=expected,
        odometer_ocr=None,
        inspection_payload=None,
    )

    assert result["view_accuracy"] == 1.0
    assert result["views"]["front"]["matched"] is True
    assert result["views"]["front"]["selected_source_frame_index"] == 210
    assert result["dashboard"]["matched"] is True
    assert result["dashboard"]["candidates"][0]["selected_timestamp_seconds"] == 10.52


def test_exit_code_fails_when_inspection_annotations_do_not_match():
    class Args:
        min_coverage = 0.75
        min_high_confidence_coverage = 0.0
        min_dashboard_candidates = 1
        min_view_accuracy = 0.8
        read_odometer = False
        min_odometer_confidence = 0.0

    manifest = {
        "summary": {
            "coverage_ratio": 1.0,
            "high_confidence_coverage_ratio": 1.0,
            "dashboard_candidates": 1,
            "frames_extracted": 4,
        },
        "validation": {
            "inspection": {
                "matched": False,
            },
        },
    }

    assert _exit_code(manifest, Args()) == 2


def test_exit_code_fails_when_required_visual_analysis_is_unavailable():
    class Args:
        min_coverage = 0.75
        min_high_confidence_coverage = 0.0
        min_dashboard_candidates = 1
        min_view_accuracy = 0.8
        read_odometer = False
        min_odometer_confidence = 0.0
        require_visual_analysis = True

    manifest = {
        "summary": {
            "coverage_ratio": 1.0,
            "high_confidence_coverage_ratio": 1.0,
            "dashboard_candidates": 1,
            "frames_extracted": 4,
        },
        "inspection": {
            "visual_analysis": {
                "available": False,
                "reason": "Gemini API unavailable: quota exceeded",
            },
        },
    }

    assert _exit_code(manifest, Args()) == 2
