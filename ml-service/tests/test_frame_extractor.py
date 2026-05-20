import asyncio
import json

import cv2
import numpy as np

from src.services.frame_extractor import FrameExtractor


def test_frame_interval_respects_requested_extraction_fps():
    assert FrameExtractor(fps=1)._frame_interval(60.0) == 60
    assert FrameExtractor(fps=2)._frame_interval(60.0) == 30
    assert FrameExtractor(fps=10)._frame_interval(60.0) == 6


def test_frame_interval_is_never_below_one():
    assert FrameExtractor(fps=120)._frame_interval(60.0) == 1
    assert FrameExtractor(fps=2)._frame_interval(0.0) == 15


def test_extract_frames_writes_source_timeline_metadata(temp_dir):
    video_path = temp_dir / "walkaround.mp4"
    output_dir = temp_dir / "frames"
    writer = cv2.VideoWriter(
        str(video_path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        10.0,
        (120, 80),
    )
    for i in range(12):
        frame = np.full((80, 120, 3), 80 + i * 8, dtype=np.uint8)
        cv2.putText(frame, str(i), (20, 45), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
        writer.write(frame)
    writer.release()

    frames = asyncio.run(
        FrameExtractor(fps=2, min_blur_threshold=0).extract_frames(
            str(video_path),
            str(output_dir),
        )
    )

    metadata = json.loads((output_dir / "frame_metadata.json").read_text(encoding="utf-8"))
    assert len(frames) == metadata["frames_extracted"]
    assert metadata["frame_interval"] == 5
    assert metadata["jpeg_quality"] == 98
    assert metadata["image_enhancement"] == "none_source_preserved"
    assert metadata["pipelines"]["inspection_frames"].startswith("source-preserved")
    assert metadata["frames"][0]["extracted_index"] == 0
    assert metadata["frames"][0]["source_frame_index"] == 0
    assert metadata["frames"][0]["inspection_path"] == metadata["frames"][0]["path"]
    assert metadata["frames"][0]["preview_path"]
    assert metadata["frames"][0]["quality_score"] >= 0
    assert metadata["frames"][0]["exposure_state"] == "ok"


def test_duplicate_filter_keeps_small_walkaround_changes():
    extractor = FrameExtractor()
    base = np.full((120, 180, 3), 140, dtype=np.uint8)
    changed = base.copy()
    cv2.rectangle(changed, (120, 30), (160, 90), (20, 20, 20), -1)

    assert extractor._is_duplicate(base, changed) is False


def test_quality_rejection_detects_extreme_exposure():
    extractor = FrameExtractor(min_blur_threshold=0)
    overexposed = np.full((120, 180, 3), 255, dtype=np.uint8)
    underexposed = np.zeros((120, 180, 3), dtype=np.uint8)

    assert extractor._quality_rejection(extractor._assess_frame_quality(overexposed)) == "overexposed"
    assert extractor._quality_rejection(extractor._assess_frame_quality(underexposed)) == "underexposed"
