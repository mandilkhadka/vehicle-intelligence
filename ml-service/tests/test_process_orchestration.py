import asyncio
import os
import shutil
from pathlib import Path
from types import SimpleNamespace

from src.api.process import (
    ProcessRequest,
    RetryVlmRequest,
    _apply_vlm_verification_filter,
    _build_process_pipeline_audit,
    _ground_vlm_locations,
    _merge_visual_damage_categories,
    _merge_vehicle_identity_override,
    _process_named_view_evidence,
    process_video,
    retry_vlm_analysis,
)


class FakeFrameExtractor:
    async def extract_frames(self, video_path, output_dir):
        frame_dir = Path(output_dir)
        frame_dir.mkdir(parents=True, exist_ok=True)
        frame = frame_dir / "frame_000001.jpg"
        frame.write_bytes(b"frame")
        return [str(frame)]


class FakeFrameOrganizer:
    async def organize(self, frames, inspection_id):
        assert frames and os.path.isabs(frames[0])
        frame = Path(frames[0])
        organized = frame.parent / "organized" / "front.jpg"
        crop = frame.parent / "organized" / "odometer_crop.jpg"
        readout = frame.parent / "organized" / "odometer_readout.jpg"
        organized.parent.mkdir(parents=True, exist_ok=True)
        organized.write_bytes(b"organized")
        crop.write_bytes(b"crop")
        readout.write_bytes(b"readout")
        return {
            "angle_shots": {
                "front": {
                    "view": "front",
                    "frame": frames[0],
                    "organized_path": str(organized),
                    "frame_index": 0,
                    "extracted_index": 0,
                    "source_frame_index": 12,
                    "timestamp_seconds": 0.4,
                    "confidence": 0.91,
                    "quality_score": 0.9,
                    "high_confidence": True,
                },
            },
            "dashboard_candidates": [
                {
                    "view": "odometer",
                    "frame": frames[0],
                    "organized_path": str(organized),
                    "crop_path": str(crop),
                    "readout_crop_path": str(readout),
                    "frame_index": 0,
                    "extracted_index": 0,
                    "source_frame_index": 12,
                    "timestamp_seconds": 0.4,
                    "confidence": 0.88,
                    "quality_score": 0.92,
                    "high_confidence": True,
                },
            ],
            "representative_frames": [
                {
                    "view": "front",
                    "frame": str(organized),
                    "frame_index": 0,
                    "extracted_index": 0,
                    "source_frame_index": 12,
                    "timestamp_seconds": 0.4,
                    "confidence": 0.91,
                    "quality_score": 0.9,
                },
            ],
            "coverage": {
                "ratio": 0.125,
                "high_confidence_ratio": 0.125,
                "present_views": ["front"],
                "missing_views": ["front-left", "left", "rear-left", "rear", "rear-right", "right", "front-right"],
            },
            "extraction_metadata": {
                "frames_extracted": 1,
                "video_duration_seconds": 1.0,
                "first_timestamp_seconds": 0.0,
                "last_timestamp_seconds": 1.0,
                "temporal_coverage_ratio": 1.0,
            },
            "method": "test",
            "frames_analyzed": 1,
            "frames_total": 1,
        }


class FakeVehicleIdentifier:
    def __init__(self):
        self.seen_frames = None

    async def identify(self, frames):
        self.seen_frames = frames
        assert frames and os.path.isabs(frames[0])
        assert Path(frames[0]).exists()
        assert frames[0].endswith("organized/front.jpg")
        return {
            "type": "car",
            "brand": "Test",
            "model": "Path",
            "vehicle_category": "test category",
            "confidence": 0.9,
        }


class FakeDashboardDetector:
    async def detect(self, frames):
        raise AssertionError("dashboard detector should be bypassed when organizer provides odometer crops")


class FakeOdometerReader:
    def __init__(self):
        self.seen_frames = None

    async def read(self, frames):
        self.seen_frames = frames
        assert frames and os.path.isabs(frames[0])
        assert frames[0].endswith("odometer_readout.jpg")
        return {"value": 123456, "confidence": 0.87, "speedometer_image_path": frames[0]}


class FakeDamageDetector:
    def __init__(self):
        self.seen_frames = None

    async def detect(self, frames, inspection_id):
        self.seen_frames = frames
        assert frames and os.path.isabs(frames[0])
        assert frames[0].endswith("organized/front.jpg")
        return {
            "severity": "low",
            "locations": [
                {
                    "type": "scratch",
                    "severity": "minor",
                    "frame": frames[0],
                }
            ],
            "scratches": {"count": 1, "detected": True},
            "dents": {"count": 0, "detected": False},
            "rust": {"count": 0, "detected": False},
            "cracks": {"count": 0, "detected": False},
            "paint_damage": {"count": 1, "detected": True},
        }


class FakeExhaustClassifier:
    def __init__(self):
        self.seen_frames = None

    async def classify(self, frames, inspection_id):
        self.seen_frames = frames
        assert frames and os.path.isabs(frames[0])
        assert frames[0].endswith("organized/front.jpg")
        return {"type": "stock", "confidence": 0.8}


class FakeModificationDetector:
    def __init__(self):
        self.seen_frames = None
        self.seen_exhaust = None

    async def detect(self, frames, frame_analysis, exhaust):
        self.seen_frames = frames
        self.seen_exhaust = exhaust
        assert frames and os.path.isabs(frames[0])
        assert frames[0].endswith("organized/front.jpg")
        assert frame_analysis["angle_shots"]["front"]["organized_path"].endswith("organized/front.jpg")
        assert exhaust["type"] == "stock"
        return {
            "available": True,
            "method": "test_local_modification",
            "summary": "Local modification scan found stock wheels and lights.",
            "items": [
                {
                    "part": "wheels",
                    "status": "stock",
                    "confidence": 0.73,
                    "frame": frames[0],
                    "source": "local_clip",
                },
                {
                    "part": "lights",
                    "status": "stock",
                    "confidence": 0.71,
                    "frame": frames[0],
                    "source": "local_clip",
                },
            ],
        }


class FakeReportGenerator:
    def __init__(self):
        self.seen_data = None

    async def generate(self, data):
        self.seen_data = data
        assert data["vehicle_info"]["brand"] == "Gemini"
        assert data["vehicle_info"]["model"] == "Vision"
        assert data["vehicle_info"]["year"] == 2024
        assert data["vehicle_info"]["variant"] == "Touring"
        assert data["odometer"]["value"] == 123456
        assert data["odometer"]["source_frame_index"] == 12
        assert data["odometer"]["timestamp_seconds"] == 0.4
        assert data["damage"]["locations"][0]["frame"].startswith("frames/")
        assert data["damage"]["locations"][0]["linked_view"] == "front"
        assert data["damage"]["locations"][0]["source_frame_index"] == 12
        assert data["damage"]["broken_lights"]["count"] == 1
        assert data["damage"]["locations"][1]["type"] == "broken_light"
        assert data["damage"]["locations"][1]["linked_view"] == "front"
        assert data["gemini_analysis"]["damage_items"][0]["type"] == "scratch"
        assert data["gemini_analysis"]["modification_items"][0]["part"] == "wheels"
        assert data["modification"]["items"][0]["part"] == "wheels"
        assert data["modification"]["items"][0]["frame"].startswith("frames/")
        assert data["frame_analysis"]["dashboard_candidates"][0]["crop_path"].startswith("frames/")
        assert data["frame_analysis"]["dashboard_candidates"][0]["readout_crop_path"].startswith("frames/")
        return {
            "summary": "ok",
            "modification_assessment": {
                "summary": "Aftermarket wheels.",
                "items": data["gemini_analysis"]["modification_items"],
            },
        }


class FakeGeminiAnalyzer:
    def __init__(self):
        self.seen_frames = None
        self.seen_analysis = None

    async def analyze(self, frames, frame_analysis=None):
        self.seen_frames = frames
        self.seen_analysis = frame_analysis
        assert frames and os.path.isabs(frames[0])
        assert frame_analysis["representative_frames"][0]["frame"].endswith("organized/front.jpg")
        return {
            "available": True,
            "vehicle": {
                "type": "SUV",
                "brand": "Gemini",
                "model": "Vision",
                "year": 2024,
                "variant": "Touring",
                "confidence": 0.96,
            },
            "overall_condition": "good",
            "damage_items": [
                {
                    "type": "scratch",
                    "location": "front bumper",
                    "severity": "minor",
                    "frame": frames[0],
                    "organizer_view": "front",
                    "frame_index": 1,
                    "source_frame_index": 12,
                    "timestamp_seconds": 0.4,
                    "confidence": 0.82,
                },
                {
                    "type": "broken_light",
                    "location": "front lamp",
                    "severity": "high",
                    "frame": frames[0],
                    "organizer_view": "front",
                    "frame_index": 1,
                    "source_frame_index": 12,
                    "timestamp_seconds": 0.4,
                    "confidence": 0.91,
                }
            ],
            "modification_items": [
                {
                    "part": "wheels",
                    "status": "modified",
                    "frame": frames[0],
                    "frame_index": 1,
                    "source_frame_index": 12,
                    "timestamp_seconds": 0.4,
                    "confidence": 0.77,
                    "notes": "Aftermarket wheels.",
                },
                {
                    "part": "lights",
                    "status": "stock",
                    "frame": frames[0],
                    "frame_index": 1,
                    "source_frame_index": 12,
                    "timestamp_seconds": 0.4,
                    "confidence": 0.74,
                    "notes": "Factory lighting.",
                },
                {
                    "part": "body",
                    "status": "stock",
                    "frame": frames[0],
                    "frame_index": 1,
                    "source_frame_index": 12,
                    "timestamp_seconds": 0.4,
                    "confidence": 0.72,
                    "notes": "No body kit visible.",
                },
            ],
            "modification_findings": "Aftermarket wheels.",
            "per_frame": [
                {
                    "frame": frames[0],
                    "view": "front",
                    "organizer_view": "front",
                    "frame_index": 0,
                    "extracted_index": 0,
                    "source_frame_index": 12,
                    "timestamp_seconds": 0.4,
                    "observations": ["front view"],
                }
            ],
            "reference_image": {
                "description": "same model reference",
                "search_query": "Gemini Vision 2024 Touring",
            },
        }


def test_process_video_routes_absolute_paths_to_ml_and_relative_paths_to_response():
    repo_root = Path(__file__).resolve().parents[2]
    uploads = repo_root / "backend" / "uploads"
    inspection_id = "codex-process-orchestration-test"
    video = uploads / "videos" / f"{inspection_id}.mov"
    video.parent.mkdir(parents=True, exist_ok=True)
    video.write_bytes(b"video")

    vehicle_identifier = FakeVehicleIdentifier()
    odometer_reader = FakeOdometerReader()
    gemini_analyzer = FakeGeminiAnalyzer()
    report_generator = FakeReportGenerator()
    modification_detector = FakeModificationDetector()
    damage_detector = FakeDamageDetector()
    exhaust_classifier = FakeExhaustClassifier()
    app = SimpleNamespace(
        state=SimpleNamespace(
            ml_services=(
                FakeFrameExtractor(),
                FakeFrameOrganizer(),
                vehicle_identifier,
                FakeDashboardDetector(),
                odometer_reader,
                damage_detector,
                exhaust_classifier,
                modification_detector,
                report_generator,
                gemini_analyzer,
            )
        )
    )

    try:
        response = asyncio.run(
            process_video(
                ProcessRequest(video_path=str(video), inspection_id=inspection_id),
                SimpleNamespace(app=app),
            )
        )
    finally:
        video.unlink(missing_ok=True)
        shutil.rmtree(uploads / "frames" / inspection_id, ignore_errors=True)

    assert vehicle_identifier.seen_frames and os.path.isabs(vehicle_identifier.seen_frames[0])
    assert vehicle_identifier.seen_frames[0].endswith("organized/front.jpg")
    assert damage_detector.seen_frames and damage_detector.seen_frames[0].endswith("organized/front.jpg")
    assert exhaust_classifier.seen_frames and exhaust_classifier.seen_frames[0].endswith("organized/front.jpg")
    assert modification_detector.seen_frames and modification_detector.seen_frames[0].endswith("organized/front.jpg")
    assert odometer_reader.seen_frames and odometer_reader.seen_frames[0].endswith("odometer_readout.jpg")
    assert gemini_analyzer.seen_frames and os.path.isabs(gemini_analyzer.seen_frames[0])
    assert report_generator.seen_data["vehicle_info"]["confidence"] == 0.96
    assert response.frames == [f"frames/{inspection_id}/frame_000001.jpg"]
    assert response.frame_analysis["angle_shots"]["front"]["frame"].startswith("frames/")
    assert response.frame_analysis["dashboard_candidates"][0]["crop_path"].startswith("frames/")
    assert response.frame_analysis["dashboard_candidates"][0]["readout_crop_path"].startswith("frames/")
    assert response.vehicle_info["brand"] == "Gemini"
    assert response.vehicle_info["model"] == "Vision"
    assert response.vehicle_info["year"] == 2024
    assert response.vehicle_info["variant"] == "Touring"
    assert response.damage["locations"][0]["frame"].startswith("frames/")
    assert response.damage["locations"][0]["angle"] == "front"
    assert response.damage["locations"][0]["linked_view"] == "front"
    assert response.damage["locations"][0]["source_frame_index"] == 12
    assert response.damage["locations"][0]["timestamp_seconds"] == 0.4
    assert response.odometer["speedometer_image_path"].endswith("odometer_readout.jpg")
    assert response.odometer["source_frame_index"] == 12
    assert response.odometer["timestamp_seconds"] == 0.4
    assert response.odometer["source_frame_path"].startswith("frames/")
    assert response.odometer["organized_frame_path"].startswith("frames/")
    assert response.odometer["crop_path"].startswith("frames/")
    assert response.odometer["readout_crop_path"].startswith("frames/")
    assert response.report["frame_analysis"] == response.frame_analysis
    assert response.inspection_analysis["sections"]["front"][0]["frame"].startswith("frames/")
    assert response.report["inspection_analysis"] == response.inspection_analysis
    assert response.report["local_modification_analysis"]["items"][0]["frame"].startswith("frames/")
    assert response.report["gemini_analysis"]["modification_items"][0]["part"] == "wheels"
    assert response.report["gemini_analysis"]["damage_items"][0]["frame"].startswith("frames/")
    assert response.report["gemini_analysis"]["modification_items"][0]["frame"].startswith("frames/")
    assert response.report["pipeline_audit"]["status"] == "incomplete"
    audit_checks = {
        check["id"]: check
        for check in response.report["pipeline_audit"]["checks"]
    }
    assert audit_checks["visual_analysis_available"]["passed"] is True
    assert audit_checks["odometer_verified"]["passed"] is True
    assert audit_checks["vehicle_identity"]["passed"] is True
    assert audit_checks["modification_detection"]["passed"] is True
    assert audit_checks["vehicle_angle_coverage"]["passed"] is False
    assert response.gemini_analysis["per_frame"][0]["frame"].startswith("frames/")
    assert response.gemini_analysis["per_frame"][0]["source_frame_index"] == 12
    assert response.gemini_analysis["per_frame"][0]["timestamp_seconds"] == 0.4
    assert response.reference_image["search_query"] == "Gemini Vision 2024 Touring"


class NonDictVehicleIdentifier:
    """Simulates a regressed service returning the wrong type."""

    async def identify(self, frames):
        return ["not", "a", "dict"]


def test_process_video_records_stage_failure_for_non_dict_results():
    repo_root = Path(__file__).resolve().parents[2]
    uploads = repo_root / "backend" / "uploads"
    inspection_id = "codex-non-dict-stage-test"
    video = uploads / "videos" / f"{inspection_id}.mov"
    video.parent.mkdir(parents=True, exist_ok=True)
    video.write_bytes(b"video")

    app = SimpleNamespace(
        state=SimpleNamespace(
            ml_services=(
                FakeFrameExtractor(),
                FakeFrameOrganizer(),
                NonDictVehicleIdentifier(),
                FakeDashboardDetector(),
                FakeOdometerReader(),
                FakeDamageDetector(),
                FakeExhaustClassifier(),
                FakeModificationDetector(),
                FakeReportGenerator(),
                FakeGeminiAnalyzer(),
            )
        )
    )

    try:
        response = asyncio.run(
            process_video(
                ProcessRequest(video_path=str(video), inspection_id=inspection_id),
                SimpleNamespace(app=app),
            )
        )
    finally:
        video.unlink(missing_ok=True)
        shutil.rmtree(uploads / "frames" / inspection_id, ignore_errors=True)

    stage = response.report["stage_status"]["vehicle_id"]
    assert stage["ok"] is False
    assert stage["error"]
    assert response.report["partial"] is True
    # The stage degraded to its fallback, then the Gemini identity merge still applied.
    assert response.vehicle_info["brand"] == "Gemini"


def test_process_pipeline_audit_surfaces_low_confidence_and_unavailable_evidence():
    audit = _build_process_pipeline_audit(
        frame_analysis={
            "coverage": {
                "ratio": 1.0,
                "high_confidence_ratio": 0.67,
                "present_views": [
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
                    "wheels",
                    "trunk",
                    "engine-bay",
                ],
                "missing_views": [],
            },
            "angle_shots": {
                "front": {
                    "view": "front",
                    "organized_path": "/tmp/front.jpg",
                    "quality_score": 0.91,
                }
            },
            "dashboard_candidates": [
                {
                    "view": "odometer",
                    "organized_path": "/tmp/odometer.jpg",
                    "quality_score": 0.88,
                }
            ],
            "extraction_metadata": {
                "frames_extracted": 56,
                "video_duration_seconds": 29.0,
                "first_timestamp_seconds": 0.0,
                "last_timestamp_seconds": 28.5,
                "temporal_coverage_ratio": 0.9828,
            },
            "frames_total": 56,
            "frames_analyzed": 56,
        },
        vehicle_info={
            "type": "car",
            "brand": "Nissan",
            "model": "",
            "confidence": 0.36,
        },
        odometer={
            "value": 12192,
            "confidence": 0.42,
            "reason": "Local OCR produced only low-confidence candidates.",
        },
        damage={
            "severity": "high",
            "locations": [{"type": "scratch", "severity": "major"}],
            "scratches": {"count": 1, "detected": True},
            "dents": {"count": 0, "detected": False},
            "rust": {"count": 0, "detected": False},
            "cracks": {"count": 0, "detected": False},
            "paint_damage": {"count": 0, "detected": False},
            "wheel_damage": {"count": 0, "detected": False},
            "broken_lights": {"count": 0, "detected": False},
            "missing_parts": {"count": 0, "detected": False},
            "panel_misalignment": {"count": 0, "detected": False},
        },
        exhaust={"type": "stock", "confidence": 0.8},
        report={
            "summary": "Vehicle inspection completed.",
            "vehicle_details": {"condition": "poor"},
            "visual_analysis": {
                "available": False,
                "reason": "Gemini API quota exceeded.",
            },
            "modification_assessment": {
                "items": [
                    {
                        "part": "exhaust",
                        "status": "stock",
                        "confidence": 0.8,
                    },
                    {
                        "part": "wheels",
                        "status": "stock",
                        "confidence": 0.7,
                    },
                    {
                        "part": "lights",
                        "status": "stock",
                        "confidence": 0.7,
                    },
                ],
            },
        },
        gemini_analysis={
            "available": False,
            "reason": "Gemini API quota exceeded.",
            "damage_items": [],
            "modification_items": [],
        },
        inspection_analysis={
            "available": True,
            "sections": {
                "front": [
                    {
                        "section": "front",
                        "frame": "/tmp/front.jpg",
                        "confidence": 0.82,
                    }
                ]
            },
            "rejected_images": [],
            "consistency": {"conflicts_resolved": [], "rejected_count": 0},
        },
    )

    checks = {check["id"]: check for check in audit["checks"]}
    assert audit["status"] == "incomplete"
    assert checks["frame_extraction"]["passed"] is True
    assert checks["full_video_temporal_coverage"]["passed"] is True
    assert checks["vehicle_angle_coverage"]["passed"] is True
    assert checks["high_confidence_angle_coverage"]["passed"] is True
    assert checks["dashboard_odometer_candidates"]["passed"] is True
    assert checks["damage_detection"]["passed"] is True
    assert checks["modification_detection"]["passed"] is True
    assert checks["inspection_summary"]["passed"] is True
    assert checks["odometer_verified"]["passed"] is False
    assert checks["visual_analysis_available"]["passed"] is False
    assert checks["vehicle_identity"]["passed"] is False
    assert set(audit["missing"]) == {
        "odometer_verified",
        "visual_analysis_available",
        "vehicle_identity",
    }


def test_process_pipeline_audit_fails_closed_without_section_routing():
    audit = _build_process_pipeline_audit(
        frame_analysis={
            "coverage": {"ratio": 0.0, "high_confidence_ratio": 0.0, "present_views": []},
            "angle_shots": {},
            "dashboard_candidates": [],
            "extraction_metadata": {},
        },
        vehicle_info={},
        odometer={},
        damage={},
        exhaust={},
        report={},
        gemini_analysis={"available": False},
        inspection_analysis=None,
    )

    checks = {check["id"]: check for check in audit["checks"]}
    assert checks["inspection_section_routing"]["passed"] is False
    assert checks["inspection_section_routing"]["evidence"]["not_supplied"] is True


def test_vehicle_identity_override_supplies_exact_year_and_variant():
    merged = _merge_vehicle_identity_override(
        {
            "type": "car",
            "brand": "Toyota",
            "model": "Sienta",
            "vehicle_category": "compact minivan",
            "year_range": "2022-present",
            "variant_candidates": ["Hybrid", "Z", "G", "X"],
            "confidence": 0.55,
            "identity_notes": "Exact year and trim require VLM.",
        },
        {
            "source": "registration",
            "year": "2024",
            "variant": "Hybrid Z",
            "confidence": 0.98,
        },
    )

    assert merged["brand"] == "Toyota"
    assert merged["model"] == "Sienta"
    assert merged["year"] == "2024"
    assert merged["variant"] == "Hybrid Z"
    assert merged["confidence"] == 0.98
    assert merged["identity_source"] == "registration"
    assert "year" in merged["identity_override_fields"]
    assert "registration" in merged["identity_notes"]


def test_retry_vlm_analysis_uses_saved_organized_frames_and_merges_result():
    repo_root = Path(__file__).resolve().parents[2]
    uploads = repo_root / "backend" / "uploads"
    inspection_id = "codex-retry-vlm-test"
    frame = uploads / "frames" / inspection_id / "organized" / "front.jpg"
    frame.parent.mkdir(parents=True, exist_ok=True)
    frame.write_bytes(b"frame")

    gemini_analyzer = FakeGeminiAnalyzer()
    app = SimpleNamespace(state=SimpleNamespace(ml_services=(gemini_analyzer,)))

    try:
        response = asyncio.run(
            retry_vlm_analysis(
                RetryVlmRequest(
                    inspection_id=inspection_id,
                    frame_analysis={
                        "representative_frames": [
                            {
                                "view": "front",
                                "frame": f"frames/{inspection_id}/organized/front.jpg",
                            }
                        ],
                        "dashboard_candidates": [],
                        "angle_shots": {},
                    },
                    vehicle_info={
                        "brand": "Local",
                        "model": "Candidate",
                        "confidence": 0.4,
                    },
                    report={
                        "summary": "old report",
                        "pipeline_audit": {"status": "incomplete"},
                    },
                ),
                SimpleNamespace(app=app),
            )
        )
    finally:
        shutil.rmtree(uploads / "frames" / inspection_id, ignore_errors=True)

    assert gemini_analyzer.seen_frames == [str(frame)]
    assert response.gemini_analysis["available"] is True
    assert response.gemini_analysis["damage_items"][0]["frame"].startswith("frames/")
    assert response.vehicle_info["brand"] == "Gemini"
    assert response.vehicle_info["year"] == 2024
    assert response.report["visual_analysis"]["available"] is True
    assert response.report["inspection_analysis"]["available"] is True
    assert response.report["vehicle_details"]["model"] == "Vision"
    assert "pipeline_audit" not in response.report


def test_merge_visual_damage_categories_adds_requested_buckets_and_locations():
    damage = {
        "locations": [],
        "scratches": {"count": 0, "detected": False},
    }
    gemini = {
        "damage_items": [
            {
                "type": "panel_misalignment",
                "severity": "moderate",
                "confidence": 0.8,
                "frame": "frames/test/organized/rear.jpg",
                "view": "rear",
                "frame_index": 1,
                "source_frame_index": 44,
                "timestamp_seconds": 1.8,
            },
            {
                "type": "missing_part",
                "severity": "low",
                "confidence": 0.41,
                "frame": "frames/test/organized/front.jpg",
                "view": "front",
            }
        ]
    }

    _merge_visual_damage_categories(damage, gemini)

    assert damage["wheel_damage"] == {"count": 0, "detected": False}
    assert damage["broken_lights"] == {"count": 0, "detected": False}
    assert damage["missing_parts"] == {"count": 0, "detected": False}
    assert damage["panel_misalignment"] == {"count": 1, "detected": True}
    assert damage["locations"][0]["type"] == "panel_misalignment"
    assert damage["locations"][0]["linked_view"] == "rear"


def test_named_view_audit_tracks_detail_views_without_blocking_core_coverage():
    evidence = _process_named_view_evidence(
        {
            "coverage": {
                "present_views": [
                    "front",
                    "front-left",
                    "left",
                    "rear-left",
                    "rear",
                    "rear-right",
                    "right",
                    "front-right",
                    "interior",
                ],
            },
            "dashboard_candidates": [{"view": "odometer"}],
            "angle_shots": {},
        }
    )

    assert evidence["has_required_named_views"] is True
    assert evidence["missing_named_views"] == []
    assert evidence["missing_detail_views"] == ["wheels", "trunk", "engine-bay"]


def test_ground_vlm_locations_crops_region_to_bbox_and_snapshot(tmp_path, monkeypatch):
    """A VLM finding's normalized region becomes a pixel bbox + cropped
    snapshot, so it satisfies the same location contract as the CV detector."""
    import cv2
    import numpy as np

    uploads = tmp_path / "uploads"
    monkeypatch.setenv("UPLOADS_ROOT", str(uploads))

    inspection_id = "insp123"
    frame_rel = f"frames/{inspection_id}/organized/front.jpg"
    frame_abs = uploads / frame_rel
    frame_abs.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(frame_abs), np.full((1000, 1000, 3), 128, dtype=np.uint8))

    damage_data = {
        "locations": [
            {
                "source": "vlm",
                "type": "scratch",
                "frame": frame_rel,
                # [ymin, xmin, ymax, xmax] on a 0-1000 grid -> bbox [x1,y1,x2,y2]
                "region": [100, 200, 300, 400],
                "confidence": 0.9,
            }
        ]
    }

    _ground_vlm_locations(damage_data, inspection_id, backend_root=str(tmp_path))

    loc = damage_data["locations"][0]
    assert loc["bbox"] == [200, 100, 400, 300]
    assert "region" not in loc  # superseded by bbox
    assert loc["snapshot"].startswith(f"frames/{inspection_id}/damage_snapshots/")
    assert (uploads / loc["snapshot"]).exists()


def test_merge_visual_damage_categories_normalizes_moderate_severity():
    """VLM items say "moderate" (per the prompt schema); the merged location
    must use the shared DamageSeverity contract value "medium"."""
    damage = {"locations": []}
    gemini = {
        "damage_items": [
            {
                "type": "dent",
                "severity": "moderate",
                "confidence": 0.8,
                "frame": "frames/t/organized/front.jpg",
                "view": "front",
            }
        ]
    }

    _merge_visual_damage_categories(damage, gemini)

    assert damage["locations"][0]["severity"] == "medium"


def test_vlm_filter_recomputes_overall_severity_from_kept_locations():
    """With no dedicated detector, severity comes from the empty-result "low";
    a high-severity VLM finding must raise the top-level severity."""
    damage = {
        "severity": "low",
        "locations": [
            {"type": "dent", "source": "vlm", "severity": "high", "confidence": 0.9},
        ],
    }

    _apply_vlm_verification_filter(damage, {"available": True})

    assert damage["severity"] == "high"
    assert damage["total_count"] == 1
    assert damage["locations"][0]["vlm_verified"] is True


def test_vlm_filter_resets_severity_when_all_locations_dropped():
    damage = {
        "severity": "high",
        "locations": [
            {"type": "scratch", "source": "yolo", "confidence": 0.2},
        ],
    }

    _apply_vlm_verification_filter(damage, {"available": False})

    assert damage["locations"] == []
    assert damage["severity"] == "low"
    assert damage["total_count"] == 0


def test_vlm_filter_keeps_degraded_stage_severity_marker():
    """When the damage stage itself failed, the degraded fallback keeps its
    explicit severity marker instead of being recomputed to "low"."""
    damage = {"severity": "unknown", "available": False, "locations": []}

    _apply_vlm_verification_filter(damage, {"available": False})

    assert damage["severity"] == "unknown"


def test_ground_vlm_locations_handles_pixel_regions_and_inverted_pairs(tmp_path, monkeypatch):
    """Local VLMs often emit raw pixel coordinates (max > 1000) despite the
    0-1000 grid instruction, and occasionally inverted min/max pairs."""
    import cv2
    import numpy as np

    uploads = tmp_path / "uploads"
    monkeypatch.setenv("UPLOADS_ROOT", str(uploads))

    inspection_id = "insp-pixel"
    frame_rel = f"frames/{inspection_id}/organized/front.jpg"
    frame_abs = uploads / frame_rel
    frame_abs.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(frame_abs), np.full((1080, 1920, 3), 128, dtype=np.uint8))

    damage_data = {
        "locations": [
            {
                "source": "vlm",
                "type": "scratch",
                "frame": frame_rel,
                # raw pixels: [ymin, xmin, ymax, xmax] for a 1920x1080 frame
                "region": [100, 200, 300, 1500],
                "confidence": 0.9,
            },
            {
                "source": "vlm",
                "type": "dent",
                "frame": frame_rel,
                # inverted pairs on the 0-1000 grid -> swapped, not dropped
                "region": [300, 400, 100, 200],
                "confidence": 0.9,
            },
        ]
    }

    _ground_vlm_locations(damage_data, inspection_id, backend_root=str(tmp_path))

    pixel_loc = damage_data["locations"][0]
    assert pixel_loc["bbox"] == [200, 100, 1500, 300]
    assert pixel_loc["frame_width"] == 1920
    assert pixel_loc["frame_height"] == 1080

    inverted_loc = damage_data["locations"][1]
    # After swapping: ymin=100, xmin=200, ymax=300, xmax=400 on the 0-1000 grid.
    assert inverted_loc["bbox"] == [384, 108, 768, 324]


def test_ground_vlm_locations_skips_when_no_region(tmp_path, monkeypatch):
    monkeypatch.setenv("UPLOADS_ROOT", str(tmp_path / "uploads"))
    damage_data = {
        "locations": [
            {"source": "vlm", "type": "dent", "frame": "frames/x/organized/rear.jpg", "confidence": 0.9}
        ]
    }
    _ground_vlm_locations(damage_data, "x", backend_root=str(tmp_path))
    loc = damage_data["locations"][0]
    assert "bbox" not in loc and "snapshot" not in loc  # UI falls back to frame


def test_process_request_requires_exactly_one_media_source():
    import pytest

    with pytest.raises(ValueError):
        ProcessRequest(inspection_id="media-source-test")
    with pytest.raises(ValueError):
        ProcessRequest(
            video_path="/tmp/a.mov",
            image_paths=["/tmp/b.jpg"],
            inspection_id="media-source-test",
        )
    assert ProcessRequest(image_paths=["/tmp/b.jpg"], inspection_id="media-source-test").video_path is None
    assert ProcessRequest(video_path="/tmp/a.mov", inspection_id="media-source-test").image_paths is None


def test_prepare_photo_frames_normalizes_and_skips_unreadable(tmp_path):
    import cv2
    import numpy as np

    from src.api.process import prepare_photo_frames

    repo_root = Path(__file__).resolve().parents[2]
    backend_root = str(repo_root)
    inspection_id = "photo-frames-unit-test"

    good = tmp_path / "good.jpg"
    cv2.imwrite(str(good), np.full((32, 48, 3), 128, dtype=np.uint8))
    unreadable = tmp_path / "unreadable.jpg"
    unreadable.write_bytes(b"not an image")

    frames_dir = repo_root / "backend" / "uploads" / "frames" / inspection_id
    try:
        frames = prepare_photo_frames([str(good), str(unreadable)], inspection_id, backend_root)
        assert frames == [f"frames/{inspection_id}/frame_0000.jpg"]
        assert (frames_dir / "frame_0000.jpg").exists()
    finally:
        shutil.rmtree(frames_dir, ignore_errors=True)


def test_prepare_photo_frames_raises_400_when_no_photo_decodes(tmp_path):
    import pytest
    from fastapi import HTTPException

    from src.api.process import prepare_photo_frames

    repo_root = Path(__file__).resolve().parents[2]
    backend_root = str(repo_root)
    inspection_id = "photo-frames-none-test"

    unreadable = tmp_path / "unreadable.jpg"
    unreadable.write_bytes(b"not an image")

    frames_dir = repo_root / "backend" / "uploads" / "frames" / inspection_id
    try:
        with pytest.raises(HTTPException) as exc_info:
            prepare_photo_frames([str(unreadable)], inspection_id, backend_root)
        assert exc_info.value.status_code == 400
    finally:
        shutil.rmtree(frames_dir, ignore_errors=True)


def test_process_photo_flow_uses_uploaded_photos_as_frames():
    import cv2
    import numpy as np

    repo_root = Path(__file__).resolve().parents[2]
    uploads = repo_root / "backend" / "uploads"
    inspection_id = "photo-flow-orchestration-test"
    photo_dir = uploads / "photos" / inspection_id
    photo_dir.mkdir(parents=True, exist_ok=True)

    photo_one = photo_dir / "front.jpg"
    photo_two = photo_dir / "rear.png"
    cv2.imwrite(str(photo_one), np.full((32, 48, 3), 100, dtype=np.uint8))
    cv2.imwrite(str(photo_two), np.full((32, 48, 3), 180, dtype=np.uint8))

    app = SimpleNamespace(
        state=SimpleNamespace(
            ml_services=(
                FakeFrameExtractor(),
                FakeFrameOrganizer(),
                FakeVehicleIdentifier(),
                FakeDashboardDetector(),
                FakeOdometerReader(),
                FakeDamageDetector(),
                FakeExhaustClassifier(),
                FakeModificationDetector(),
                FakeReportGenerator(),
                FakeGeminiAnalyzer(),
            )
        )
    )

    try:
        response = asyncio.run(
            process_video(
                ProcessRequest(
                    image_paths=[str(photo_one), str(photo_two)],
                    inspection_id=inspection_id,
                ),
                SimpleNamespace(app=app),
            )
        )
    finally:
        shutil.rmtree(photo_dir, ignore_errors=True)
        shutil.rmtree(uploads / "frames" / inspection_id, ignore_errors=True)

    # Photos became the frames — no FrameExtractor involvement.
    assert response.frames == [
        f"frames/{inspection_id}/frame_0000.jpg",
        f"frames/{inspection_id}/frame_0001.jpg",
    ]
    assert response.vehicle_info["brand"] == "Gemini"
    assert response.frame_analysis["angle_shots"]["front"]["frame"].startswith("frames/")
