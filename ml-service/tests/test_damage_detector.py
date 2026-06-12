import cv2
import numpy as np

from src.services.damage_detector import DamageDetector


class _NoVehicleYolo:
    def __call__(self, frame_path):
        return []


def test_damage_detector_returns_extended_damage_categories(temp_dir):
    frame_path = temp_dir / "clean_vehicle.jpg"
    image = np.full((180, 320, 3), 128, dtype=np.uint8)
    cv2.imwrite(str(frame_path), image)

    result = DamageDetector(yolo_model=_NoVehicleYolo())._detect_sync([str(frame_path)])

    assert result["scratches"] == {"count": 0, "detected": False}
    assert result["dents"] == {"count": 0, "detected": False}
    assert result["rust"] == {"count": 0, "detected": False}
    assert result["cracks"] == {"count": 0, "detected": False}
    assert result["paint_damage"] == {"count": 0, "detected": False}
    assert result["wheel_damage"] == {"count": 0, "detected": False}
    assert result["broken_lights"] == {"count": 0, "detected": False}
    assert result["missing_parts"] == {"count": 0, "detected": False}
    assert result["panel_misalignment"] == {"count": 0, "detected": False}
    assert result["severity"] == "low"


def test_cv_heuristics_off_by_default_reports_no_damage(temp_dir, monkeypatch):
    """An edge-heavy noise image would light up the old Canny/Laplacian/HSV
    heuristics. With them disabled (the default), the detector must report
    nothing — the VLM is now the authoritative damage source."""
    import src.services.damage_detector as dd

    monkeypatch.setattr(dd, "USE_CV_HEURISTICS", False)

    frame_path = temp_dir / "noisy.jpg"
    rng = np.random.default_rng(0)
    image = rng.integers(0, 255, size=(240, 320, 3), dtype=np.uint8)
    cv2.imwrite(str(frame_path), image)

    result = dd.DamageDetector(yolo_model=_NoVehicleYolo())._detect_sync([str(frame_path)])

    assert result["locations"] == []
    assert result["total_count"] == 0
    assert result["severity"] == "low"
