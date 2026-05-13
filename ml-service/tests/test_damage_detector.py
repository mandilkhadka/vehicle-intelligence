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
    assert result["severity"] == "low"
