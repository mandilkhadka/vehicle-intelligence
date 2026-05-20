from pathlib import Path
import sys

ML_SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(ML_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(ML_SERVICE_ROOT))

from src.api.process import (
    _attach_odometer_frame_metadata,
    _dashboard_paths_from_frame_analysis,
    _frames_from_frame_analysis,
    _surface_frames_from_frame_analysis,
)
from src.services.gemini_analyzer import GeminiAnalyzer


def _touch(path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"test")
    return str(path)


def test_dashboard_paths_prefer_ocr_crops(temp_dir):
    raw = _touch(temp_dir / "raw.jpg")
    organized = _touch(temp_dir / "organized.jpg")
    crop = _touch(temp_dir / "crop.jpg")
    readout = _touch(temp_dir / "readout.jpg")

    frame_analysis = {
        "dashboard_candidates": [
            {
                "frame": raw,
                "organized_path": organized,
                "crop_path": crop,
                "readout_crop_path": readout,
            }
        ],
        "angle_shots": {
            "dashboard": {
                "frame": raw,
                "organized_path": organized,
            }
        },
    }

    assert _dashboard_paths_from_frame_analysis(frame_analysis) == [readout, organized]


def test_odometer_metadata_uses_selected_dashboard_candidate(temp_dir):
    raw = _touch(temp_dir / "raw.jpg")
    organized = _touch(temp_dir / "organized.jpg")
    crop = _touch(temp_dir / "crop.jpg")
    readout = _touch(temp_dir / "readout.jpg")

    frame_analysis = {
        "dashboard_candidates": [
            {
                "view": "dashboard",
                "frame": raw,
                "organized_path": organized,
                "crop_path": crop,
                "readout_crop_path": readout,
                "frame_index": 4,
                "extracted_index": 7,
                "source_frame_index": 210,
                "timestamp_seconds": 3.5,
                "score": 0.88,
                "high_confidence": True,
            }
        ],
    }
    odometer = {"value": 123456, "confidence": 0.9, "speedometer_image_path": readout}

    _attach_odometer_frame_metadata(odometer, frame_analysis)

    assert odometer["organizer_view"] == "dashboard"
    assert odometer["frame_index"] == 4
    assert odometer["extracted_index"] == 7
    assert odometer["source_frame_index"] == 210
    assert odometer["timestamp_seconds"] == 3.5
    assert odometer["organizer_score"] == 0.88
    assert odometer["high_confidence"] is True
    assert odometer["source_frame_path"] == raw
    assert odometer["organized_frame_path"] == organized
    assert odometer["crop_path"] == crop
    assert odometer["readout_crop_path"] == readout


def test_vlm_frames_prefer_representative_organized_frames(temp_dir):
    front = _touch(temp_dir / "organized" / "front.jpg")
    rear = _touch(temp_dir / "organized" / "rear.jpg")
    dash = _touch(temp_dir / "organized" / "dashboard.jpg")
    fallback = _touch(temp_dir / "fallback.jpg")

    frame_analysis = {
        "representative_frames": [
            {"view": "front", "frame": front},
            {"view": "rear", "frame": rear},
        ],
        "dashboard_candidates": [
            {"view": "dashboard", "organized_path": dash},
        ],
    }

    assert _frames_from_frame_analysis(frame_analysis, [fallback]) == [front, rear, dash]


def test_surface_frames_use_exterior_angle_shots_without_dashboard_candidates(temp_dir):
    front = _touch(temp_dir / "organized" / "front.jpg")
    rear = _touch(temp_dir / "organized" / "rear.jpg")
    dashboard = _touch(temp_dir / "organized" / "dashboard.jpg")
    raw = _touch(temp_dir / "raw.jpg")

    frame_analysis = {
        "angle_shots": {
            "front": {"organized_path": front},
            "rear": {"organized_path": rear},
            "dashboard": {"organized_path": dashboard},
        },
        "dashboard_candidates": [
            {"organized_path": dashboard},
        ],
    }

    assert _surface_frames_from_frame_analysis(frame_analysis, [raw]) == [front, rear]


def test_gemini_selection_preserves_organizer_view_order():
    frame_analysis = {
        "angle_shots": {
            "rear": {
                "organized_path": "rear.jpg",
                "extracted_index": 8,
                "source_frame_index": 240,
                "timestamp_seconds": 4.0,
            },
            "front": {
                "organized_path": "front.jpg",
                "extracted_index": 1,
                "source_frame_index": 30,
                "timestamp_seconds": 0.5,
            },
            "dashboard": {
                "organized_path": "dashboard.jpg",
                "extracted_index": 20,
                "source_frame_index": 600,
                "timestamp_seconds": 10.0,
            },
            "odometer": {
                "organized_path": "odometer.jpg",
                "extracted_index": 21,
                "source_frame_index": 630,
                "timestamp_seconds": 10.5,
            },
        },
        "dashboard_candidates": [
            {
                "organized_path": "dashboard-detail.jpg",
                "extracted_index": 22,
                "source_frame_index": 660,
                "timestamp_seconds": 11.0,
            },
        ],
    }

    selected = GeminiAnalyzer._select_frames(
        ["raw-1.jpg", "raw-2.jpg"],
        5,
        frame_analysis,
    )

    assert selected[:5] == [
        {
            "frame": "front.jpg",
            "view": "front",
            "extracted_index": 1,
            "source_frame_index": 30,
            "timestamp_seconds": 0.5,
        },
        {
            "frame": "rear.jpg",
            "view": "rear",
            "extracted_index": 8,
            "source_frame_index": 240,
            "timestamp_seconds": 4.0,
        },
        {
            "frame": "dashboard.jpg",
            "view": "dashboard",
            "extracted_index": 20,
            "source_frame_index": 600,
            "timestamp_seconds": 10.0,
        },
        {
            "frame": "odometer.jpg",
            "view": "odometer",
            "extracted_index": 21,
            "source_frame_index": 630,
            "timestamp_seconds": 10.5,
        },
        {
            "frame": "dashboard-detail.jpg",
            "view": "dashboard_candidate",
            "extracted_index": 22,
            "source_frame_index": 660,
            "timestamp_seconds": 11.0,
        },
    ]


def test_gemini_prompt_includes_selected_frame_metadata():
    analyzer = GeminiAnalyzer.__new__(GeminiAnalyzer)
    prompt = analyzer._build_prompt([
        {
            "frame": "front.jpg",
            "view": "front",
            "extracted_index": 1,
            "source_frame_index": 30,
            "timestamp_seconds": 0.5,
            "quality_score": 0.91,
            "score": 0.84,
            "high_confidence": True,
            "semantic_source": "clip",
        }
    ])

    assert "Frame 1: organizer_expected_view=front" in prompt
    assert "extracted_index=1" in prompt
    assert "source_frame_index=30" in prompt
    assert "timestamp_seconds=0.5" in prompt
    assert "quality_score=0.91" in prompt
    assert "selection_score=0.84" in prompt
    assert "high_confidence=True" in prompt
    assert "semantic_source=clip" in prompt


def test_gemini_selection_labels_odometer_candidates():
    selected = GeminiAnalyzer._select_frames(
        ["raw.jpg"],
        1,
        {
            "dashboard_candidates": [
                {
                    "view": "odometer",
                    "organized_path": "odometer-detail.jpg",
                    "extracted_index": 12,
                    "quality_score": 0.89,
                    "candidate_role": "dashboard_candidate",
                }
            ]
        },
    )

    assert selected == [
        {
            "frame": "odometer-detail.jpg",
            "view": "odometer_candidate",
            "extracted_index": 12,
            "quality_score": 0.89,
            "candidate_role": "dashboard_candidate",
        }
    ]


def test_gemini_selection_includes_all_named_views_before_dashboard_details():
    preferred = (
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
        "odometer",
    )
    frame_analysis = {
        "angle_shots": {
            view: {
                "organized_path": f"{view}.jpg",
                "quality_score": 0.9,
            }
            for view in preferred
        },
        "dashboard_candidates": [
            {
                "view": "dashboard",
                "organized_path": "dashboard-detail.jpg",
                "quality_score": 0.88,
            }
        ],
    }

    selected = GeminiAnalyzer._select_frames([], 12, frame_analysis)

    assert [item["view"] for item in selected[:11]] == list(preferred)
    assert selected[11]["view"] == "dashboard_candidate"
