import cv2
import numpy as np

from src.api.process import (
    _frame_extraction_config,
    _uploaded_odometer_image_candidates,
    get_uploads_root,
    upload_path,
)


def test_frame_extraction_config_uses_defaults(monkeypatch):
    monkeypatch.delenv("ML_FRAME_EXTRACTION_FPS", raising=False)
    monkeypatch.delenv("ML_FRAME_BLUR_THRESHOLD", raising=False)
    monkeypatch.delenv("ML_FRAME_JPEG_QUALITY", raising=False)

    assert _frame_extraction_config() == {
        "fps": 2.0,
        "min_blur_threshold": 15.0,
        "jpeg_quality": 98,
    }


def test_frame_extraction_config_uses_environment_overrides(monkeypatch):
    monkeypatch.setenv("ML_FRAME_EXTRACTION_FPS", "3")
    monkeypatch.setenv("ML_FRAME_BLUR_THRESHOLD", "22.5")
    monkeypatch.setenv("ML_FRAME_JPEG_QUALITY", "95")

    assert _frame_extraction_config() == {
        "fps": 3.0,
        "min_blur_threshold": 22.5,
        "jpeg_quality": 95,
    }


def test_uploads_root_defaults_to_backend_uploads(monkeypatch):
    monkeypatch.delenv("UPLOADS_ROOT", raising=False)

    assert get_uploads_root("/repo") == "/repo/backend/uploads"
    assert upload_path("frames/inspection-1/frame_0001.jpg", "/repo") == (
        "/repo/backend/uploads/frames/inspection-1/frame_0001.jpg"
    )


def test_uploads_root_can_be_overridden_for_container_mounts(monkeypatch):
    monkeypatch.setenv("UPLOADS_ROOT", "/app/uploads")

    assert get_uploads_root("/repo") == "/app/uploads"
    assert upload_path("frames/inspection-1/frame_0001.jpg", "/repo") == (
        "/app/uploads/frames/inspection-1/frame_0001.jpg"
    )


def test_uploaded_odometer_image_candidates_prefers_enhanced_copy(temp_dir):
    image_path = temp_dir / "odometer.jpg"
    image = np.full((120, 160, 3), 80, dtype=np.uint8)
    cv2.putText(image, "123456", (18, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (240, 240, 240), 2)
    cv2.imwrite(str(image_path), image)

    candidates = _uploaded_odometer_image_candidates(str(image_path))

    assert candidates[0].endswith("_enhanced.jpg")
    assert candidates[1] == str(image_path)
    enhanced = cv2.imread(candidates[0])
    assert enhanced is not None
    assert enhanced.shape[0] >= 900
    assert enhanced.shape[1] >= 1200
