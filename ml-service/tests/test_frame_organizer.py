import asyncio
import json
import os
from pathlib import Path

import cv2
import numpy as np

from services.frame_organizer import FrameCandidate, VehicleFrameOrganizer


def _write_frame(path: Path, brightness: int, shape: str = "vehicle") -> None:
    image = np.full((180, 320, 3), brightness, dtype=np.uint8)
    if shape == "vehicle":
        cv2.rectangle(image, (45, 55), (275, 135), (brightness // 2, brightness // 2, brightness // 2), -1)
        cv2.circle(image, (90, 140), 16, (20, 20, 20), -1)
        cv2.circle(image, (230, 140), 16, (20, 20, 20), -1)
    else:
        cv2.rectangle(image, (45, 45), (275, 135), (25, 25, 25), -1)
        cv2.rectangle(image, (120, 80), (210, 112), (220, 220, 220), -1)
        cv2.putText(image, "123456", (126, 103), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (10, 10, 10), 2)
    cv2.imwrite(str(path), image)


def test_organize_selects_angle_and_dashboard_frames(temp_dir):
    frames_dir = temp_dir / "frames" / "inspection-1"
    frames_dir.mkdir(parents=True)

    frame_paths = []
    for i in range(8):
        frame = frames_dir / f"frame_{i:04d}.jpg"
        _write_frame(frame, 150 + (i % 2) * 20, "vehicle")
        frame_paths.append(str(frame))

    dashboard = frames_dir / "frame_0008.jpg"
    _write_frame(dashboard, 70, "dashboard")
    frame_paths.append(str(dashboard))
    (frames_dir / "frame_metadata.json").write_text(
        json.dumps({
            "video_fps": 60.0,
            "total_source_frames": 270,
            "frames_extracted": len(frame_paths),
            "frames": [
                {
                    "extracted_index": i,
                    "source_frame_index": i * 30,
                    "timestamp_seconds": i * 0.5,
                    "path": path,
                    "blur_score": 120.0,
                }
                for i, path in enumerate(frame_paths)
            ]
        }),
        encoding="utf-8",
    )

    organizer = VehicleFrameOrganizer()
    result = asyncio.run(organizer.organize(frame_paths, "inspection-1"))

    assert result["frames_total"] == len(frame_paths)
    assert result["frames_analyzed"] == len(frame_paths)
    assert result["extraction_metadata"]["frames_extracted"] == len(frame_paths)
    assert result["extraction_metadata"]["temporal_coverage_ratio"] is not None
    assert result["angle_shots"]
    assert "odometer" in result["angle_shots"]
    assert result["dashboard_candidates"]
    assert result["representative_frames"]
    assert result["coverage"]["ratio"] > 0
    assert "high_confidence_ratio" in result["coverage"]
    assert all(
        shot.get("semantic_source") == "temporal_fallback"
        for shot in result["angle_shots"].values()
    )
    assert all(
        shot["source_frame_index"] == shot["extracted_index"] * 30
        for shot in result["angle_shots"].values()
    )
    assert all(
        shot["timestamp_seconds"] == shot["extracted_index"] * 0.5
        for shot in result["angle_shots"].values()
    )

    first_dashboard = result["dashboard_candidates"][0]
    assert first_dashboard["organized_path"]
    assert first_dashboard["inspection_path"] == first_dashboard["organized_path"]
    assert first_dashboard["preview_path"]
    assert first_dashboard["crop_path"]
    assert first_dashboard["source_frame_index"] == first_dashboard["extracted_index"] * 30
    assert first_dashboard["timestamp_seconds"] == first_dashboard["extracted_index"] * 0.5
    assert "high_confidence" in first_dashboard
    assert os.path.exists(first_dashboard["organized_path"])
    assert os.path.exists(first_dashboard["preview_path"])
    assert os.path.exists(first_dashboard["crop_path"])
    assert Path(first_dashboard["organized_path"]).parent.name == "organized"
    assert all(
        frame["source_frame_index"] == frame["extracted_index"] * 30
        for frame in result["representative_frames"]
    )
    assert all(
        frame["timestamp_seconds"] == frame["extracted_index"] * 0.5
        for frame in result["representative_frames"]
    )
    assert any(frame["view"] == "odometer" for frame in result["representative_frames"])
    assert all("quality_score" in frame for frame in result["representative_frames"])


def test_dashboard_crop_focuses_instrument_cluster_region(temp_dir):
    src = temp_dir / "dashboard.jpg"
    dest = temp_dir / "dashboard_crop.jpg"
    image = np.zeros((100, 200, 3), dtype=np.uint8)
    image[:, :50] = (255, 0, 0)
    image[45:58, 80:120] = (0, 255, 0)
    image[:, 160:] = (0, 0, 255)
    cv2.imwrite(str(src), image)

    crop_path = VehicleFrameOrganizer._write_dashboard_crop(str(src), dest)

    assert crop_path == str(dest)
    crop = cv2.imread(str(dest))
    assert crop is not None
    assert crop.shape[0] >= 320
    assert crop.shape[1] >= 900
    # The crop should include the central cluster area but exclude far-side
    # dashboard/window text zones that polluted OCR on real walkaround frames.
    assert crop[:, :, 1].mean() > crop[:, :, 0].mean()
    assert crop[:, :, 1].mean() > crop[:, :, 2].mean()


def test_odometer_readout_crop_extracts_numeric_display(temp_dir):
    src = temp_dir / "dashboard_crop.jpg"
    dest = temp_dir / "readout_crop.jpg"
    image = np.zeros((160, 420, 3), dtype=np.uint8)
    cv2.rectangle(image, (40, 25), (380, 130), (18, 18, 18), -1)
    cv2.putText(image, "12292km", (130, 95), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (245, 245, 245), 2)
    cv2.putText(image, "308km", (280, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (220, 220, 220), 1)
    cv2.imwrite(str(src), image)

    readout_path = VehicleFrameOrganizer._write_odometer_readout_crop(str(src), dest)

    assert readout_path == str(dest)
    crop = cv2.imread(str(dest))
    assert crop is not None
    assert crop.shape[0] >= 180
    assert crop.shape[1] >= 720
    assert float(np.mean(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) > 180)) > 0.02


def test_clip_confidence_uses_semantic_and_vehicle_evidence():
    organizer = VehicleFrameOrganizer(clip_model=object(), clip_processor=object())
    candidate = FrameCandidate(
        index=3,
        path="frame.jpg",
        blur_score=300.0,
        brightness=128.0,
        contrast=60.0,
        quality_score=0.95,
        vehicle_box=(10, 10, 200, 120),
        vehicle_ratio=0.35,
        heuristic_dashboard_score=0.2,
        view_scores={"front": 0.16, "dashboard": 0.10},
    )

    front = organizer._candidate_payload(candidate, "front", 0.48)

    assert front["semantic_source"] == "clip"
    assert front["high_confidence"] is True


def test_candidate_payload_uses_extracted_index_as_public_frame_index():
    organizer = VehicleFrameOrganizer()
    candidate = FrameCandidate(
        index=3,
        path="frame_0120.jpg",
        blur_score=300.0,
        brightness=128.0,
        contrast=60.0,
        quality_score=0.95,
        vehicle_box=(10, 10, 200, 120),
        vehicle_ratio=0.35,
        heuristic_dashboard_score=0.2,
        view_scores={"front": 0.7},
        metadata={
            "extracted_index": 120,
            "source_frame_index": 3600,
            "timestamp_seconds": 60.7,
        },
    )

    front = organizer._candidate_payload(candidate, "front", 0.48)

    assert front["frame_index"] == 120
    assert front["extracted_index"] == 120
    assert front["source_frame_index"] == 3600
    assert front["timestamp_seconds"] == 60.7


def test_dashboard_confidence_requires_dashboard_evidence():
    organizer = VehicleFrameOrganizer(clip_model=object(), clip_processor=object())
    weak_dashboard = FrameCandidate(
        index=4,
        path="frame.jpg",
        blur_score=300.0,
        brightness=128.0,
        contrast=60.0,
        quality_score=0.95,
        vehicle_box=None,
        vehicle_ratio=0.0,
        heuristic_dashboard_score=0.2,
        view_scores={"dashboard": 0.20},
    )
    strong_dashboard = FrameCandidate(
        **{
            **weak_dashboard.__dict__,
            "heuristic_dashboard_score": 0.72,
        }
    )

    assert organizer._candidate_payload(weak_dashboard, "dashboard", 0.52)["high_confidence"] is False
    assert organizer._candidate_payload(strong_dashboard, "dashboard", 0.52)["high_confidence"] is True


def test_dashboard_candidates_preserve_odometer_semantic_label():
    organizer = VehicleFrameOrganizer()
    candidate = FrameCandidate(
        index=0,
        path="dashboard.jpg",
        blur_score=300.0,
        brightness=128.0,
        contrast=60.0,
        quality_score=0.9,
        vehicle_box=None,
        vehicle_ratio=0.0,
        heuristic_dashboard_score=0.6,
        view_scores={
            "dashboard": 0.05,
            "odometer": 0.7,
        },
    )

    selected = organizer._select_dashboard_candidates([candidate])

    assert selected[0]["view"] == "odometer"
    assert selected[0]["candidate_role"] == "dashboard_candidate"


def test_detail_views_are_not_filled_from_weak_fallback_frames():
    organizer = VehicleFrameOrganizer()
    candidates = []
    for index in range(8):
        view_scores = {view: 0.01 for view in organizer._view_names}
        view_scores["interior"] = 0.7 if index >= 6 else 0.01
        view_scores["dashboard"] = 0.65 if index >= 6 else 0.01
        candidates.append(
            FrameCandidate(
                index=index,
                path=f"frame_{index:04d}.jpg",
                blur_score=300.0,
                brightness=128.0,
                contrast=60.0,
                quality_score=0.8,
                vehicle_box=None,
                vehicle_ratio=0.0,
                heuristic_dashboard_score=0.7 if index >= 6 else 0.1,
                view_scores=view_scores,
            )
        )

    selected = organizer._select_angle_shots(candidates)

    assert "interior" in selected
    assert "dashboard" in selected
    assert "wheels" not in selected
    assert "trunk" not in selected
    assert "engine-bay" not in selected


def test_detail_view_requires_clip_score_to_beat_interior_dashboard():
    organizer = VehicleFrameOrganizer(clip_model=object(), clip_processor=object())
    weak_wheels = FrameCandidate(
        index=0,
        path="interior.jpg",
        blur_score=300.0,
        brightness=128.0,
        contrast=60.0,
        quality_score=0.9,
        vehicle_box=None,
        vehicle_ratio=0.0,
        heuristic_dashboard_score=0.65,
        view_scores={
            "wheels": 0.31,
            "interior": 0.36,
            "dashboard": 0.34,
            "odometer": 0.20,
        },
    )
    strong_wheels = FrameCandidate(
        index=1,
        path="wheels.jpg",
        blur_score=300.0,
        brightness=128.0,
        contrast=60.0,
        quality_score=0.9,
        vehicle_box=None,
        vehicle_ratio=0.0,
        heuristic_dashboard_score=0.12,
        view_scores={
            "wheels": 0.48,
            "interior": 0.08,
            "dashboard": 0.06,
            "odometer": 0.03,
        },
    )

    selected = organizer._select_angle_shots([weak_wheels, strong_wheels])

    assert selected["wheels"]["frame_index"] == 1


def test_exterior_selection_prefers_walkaround_temporal_order():
    organizer = VehicleFrameOrganizer(clip_model=object(), clip_processor=object())
    candidates = []
    for index in range(8):
        view_scores = {view: 0.05 for view in organizer._view_names}
        view_scores["front"] = 0.25 if index == 0 else 0.05
        candidates.append(
            FrameCandidate(
                index=index,
                path=f"frame_{index:04d}.jpg",
                blur_score=300.0,
                brightness=128.0,
                contrast=60.0,
                quality_score=0.8,
                vehicle_box=(10, 10, 100, 60),
                vehicle_ratio=0.3,
                heuristic_dashboard_score=0.1,
                view_scores=view_scores,
            )
        )

    candidates[6].view_scores["front"] = 0.7

    selected = organizer._select_angle_shots(candidates)

    assert selected["front"]["frame_index"] == 0
    assert selected["front"]["temporal_score"] == 1.0


def test_exterior_selection_does_not_fill_missing_views_with_dashboard_frames():
    organizer = VehicleFrameOrganizer()
    candidates = []
    for index in range(10):
        is_dashboard = index >= 6
        view_scores = {view: 0.01 for view in organizer._view_names}
        if is_dashboard:
            view_scores["right"] = 0.8
            view_scores["front-right"] = 0.8
            view_scores["dashboard"] = 0.8
        candidates.append(
            FrameCandidate(
                index=index,
                path=f"frame_{index:04d}.jpg",
                blur_score=300.0,
                brightness=128.0,
                contrast=60.0,
                quality_score=0.8,
                vehicle_box=None,
                vehicle_ratio=0.0,
                heuristic_dashboard_score=0.7 if is_dashboard else 0.1,
                view_scores=view_scores,
            )
        )

    selected = organizer._select_angle_shots(candidates)

    assert "right" not in selected
    assert "front-right" not in selected
    assert selected["dashboard"]["frame_index"] >= 6


def test_clip_selection_rejects_dashboard_frames_for_exterior_views():
    organizer = VehicleFrameOrganizer(clip_model=object(), clip_processor=object())
    candidates = []
    for index, view in enumerate(("front", "front-left", "left", "rear-left", "rear")):
        view_scores = {name: 0.01 for name in organizer._view_names}
        view_scores[view] = 0.42
        candidates.append(
            FrameCandidate(
                index=index,
                path=f"frame_{index:04d}.jpg",
                blur_score=300.0,
                brightness=128.0,
                contrast=60.0,
                quality_score=0.9,
                vehicle_box=(20, 20, 250, 130),
                vehicle_ratio=0.35,
                heuristic_dashboard_score=0.1,
                view_scores=view_scores,
            )
        )

    for index, view in enumerate(("rear-right", "right", "front-right"), start=5):
        view_scores = {name: 0.01 for name in organizer._view_names}
        view_scores[view] = 0.55
        view_scores["dashboard"] = 0.60
        view_scores["odometer"] = 0.52
        candidates.append(
            FrameCandidate(
                index=index,
                path=f"dashboard_{index:04d}.jpg",
                blur_score=300.0,
                brightness=128.0,
                contrast=60.0,
                quality_score=0.9,
                vehicle_box=None,
                vehicle_ratio=0.0,
                heuristic_dashboard_score=0.78,
                view_scores=view_scores,
            )
        )

    selected = organizer._select_angle_shots(candidates)

    assert "rear-right" not in selected
    assert "right" not in selected
    assert "front-right" not in selected
    assert selected["dashboard"]["frame_index"] >= 5


def test_organized_angle_copy_preserves_source_resolution(temp_dir):
    src = temp_dir / "small.jpg"
    dest = temp_dir / "organized.jpg"
    image = np.full((240, 420, 3), 120, dtype=np.uint8)
    cv2.rectangle(image, (60, 70), (360, 180), (80, 80, 80), -1)
    cv2.imwrite(str(src), image)

    copied = VehicleFrameOrganizer._copy_frame(str(src), dest)

    assert copied == str(dest)
    out = cv2.imread(str(dest))
    assert out is not None
    assert out.shape[:2] == image.shape[:2]


def test_low_temporal_fit_blocks_exterior_high_confidence():
    organizer = VehicleFrameOrganizer(clip_model=object(), clip_processor=object())
    candidate = FrameCandidate(
        index=6,
        path="frame.jpg",
        blur_score=300.0,
        brightness=128.0,
        contrast=60.0,
        quality_score=0.95,
        vehicle_box=(10, 10, 200, 120),
        vehicle_ratio=0.35,
        heuristic_dashboard_score=0.2,
        view_scores={"front": 0.7},
    )

    front = organizer._candidate_payload(candidate, "front", 0.65, temporal_score=0.1)

    assert front["high_confidence"] is False


def test_strong_temporal_and_vehicle_evidence_can_offset_moderate_clip_score():
    organizer = VehicleFrameOrganizer(clip_model=object(), clip_processor=object())
    candidate = FrameCandidate(
        index=6,
        path="frame.jpg",
        blur_score=300.0,
        brightness=128.0,
        contrast=60.0,
        quality_score=0.95,
        vehicle_box=(10, 10, 200, 120),
        vehicle_ratio=0.5,
        heuristic_dashboard_score=0.2,
        view_scores={"right": 0.08},
    )

    right = organizer._candidate_payload(candidate, "right", 0.58, temporal_score=0.95)

    assert right["high_confidence"] is True


def test_dashboard_candidates_reject_obvious_exterior_vehicle_frames():
    organizer = VehicleFrameOrganizer(yolo_model=object(), clip_model=object(), clip_processor=object())
    dashboard = FrameCandidate(
        index=0,
        path="dashboard.jpg",
        blur_score=300.0,
        brightness=128.0,
        contrast=60.0,
        quality_score=0.9,
        vehicle_box=None,
        vehicle_ratio=0.02,
        heuristic_dashboard_score=0.74,
        view_scores={"dashboard": 0.24, "odometer": 0.10},
    )
    exterior = FrameCandidate(
        index=1,
        path="exterior.jpg",
        blur_score=300.0,
        brightness=128.0,
        contrast=60.0,
        quality_score=0.9,
        vehicle_box=(0, 0, 400, 300),
        vehicle_ratio=0.82,
        heuristic_dashboard_score=0.30,
        view_scores={"dashboard": 0.35, "odometer": 0.08},
    )

    selected = organizer._select_dashboard_candidates([exterior, dashboard])

    assert [item["frame_index"] for item in selected] == [0]
