"""
Dedicated damage detection model.

Runs an automotive-damage detection/segmentation model (e.g. YOLO11/YOLO12 or
RT-DETR fine-tuned on CarDD — see ml-service/training/) over the organized
exterior frames and emits damage locations in the exact contract the rest of
the pipeline consumes (panel inference, repair costs, rationale, frontend
snapshot cards): ``type``, ``confidence``, ``severity``, ``frame``, ``bbox``,
``snapshot``, plus optional ``mask`` polygons from segmentation models.

CLIP plays no role here — it is used upstream only for frame selection and
vehicle identification. This detector is the primary damage source when
``ML_DAMAGE_MODEL_PATH`` is configured; the VLM remains a complementary source
for categories outside the training taxonomy (rust, missing parts, ...).
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return float(default)
    try:
        return float(raw)
    except ValueError:
        logger.warning("Invalid %s=%r; using default %s", name, raw, default)
        return float(default)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return int(default)
    try:
        return int(raw)
    except ValueError:
        logger.warning("Invalid %s=%r; using default %s", name, raw, default)
        return int(default)


# Inference tuning (env-overridable, no code changes needed to retune).
MODEL_CONFIDENCE = _env_float("ML_DAMAGE_MODEL_CONFIDENCE", 0.35)
MODEL_IOU = _env_float("ML_DAMAGE_MODEL_IOU", 0.50)
MODEL_IMGSZ = _env_int("ML_DAMAGE_MODEL_IMGSZ", 1024)
# Cap polygon vertices per mask so response payloads stay small.
_MAX_MASK_POINTS = 160

# CarDD class names → the pipeline's damage location taxonomy. Keys are
# normalized (lowercase, spaces/hyphens → underscores). Must stay in sync with
# TAXONOMY in backend/scripts/export-training-set.ts. Override or extend with
# ML_DAMAGE_CLASS_MAP='{"model_class": "pipeline_type", ...}'.
DEFAULT_CLASS_MAP: Dict[str, str] = {
    "dent": "dent",
    "scratch": "scratch",
    "crack": "crack",
    "glass_shatter": "crack",
    "lamp_broken": "broken_light",
    "tire_flat": "wheel_damage",
    # Extra automotive-damage classes some datasets/models provide.
    "rust": "rust",
    "paint_damage": "paint_damage",
    "paint_chip": "paint_damage",
    "wheel_damage": "wheel_damage",
    "broken_light": "broken_light",
    "missing_part": "missing_part",
    "panel_misalignment": "panel_misalignment",
}

# Location `type` → structured category key on the damage dict. Mirrors the
# mapping in src/api/process.py.
_TYPE_TO_CATEGORY: Dict[str, str] = {
    "scratch": "scratches",
    "dent": "dents",
    "rust": "rust",
    "crack": "cracks",
    "paint_damage": "paint_damage",
    "wheel_damage": "wheel_damage",
    "broken_light": "broken_lights",
    "missing_part": "missing_parts",
    "panel_misalignment": "panel_misalignment",
}

_CATEGORIES = (
    "scratches", "dents", "rust", "cracks", "paint_damage",
    "wheel_damage", "broken_lights", "missing_parts", "panel_misalignment",
)


def _normalize_class_name(name: Any) -> str:
    return str(name or "").strip().lower().replace("-", "_").replace(" ", "_")


def load_class_map() -> Dict[str, str]:
    """Default CarDD class map merged with the ML_DAMAGE_CLASS_MAP env JSON."""
    class_map = dict(DEFAULT_CLASS_MAP)
    raw = os.getenv("ML_DAMAGE_CLASS_MAP", "").strip()
    if not raw:
        return class_map
    try:
        override = json.loads(raw)
        if not isinstance(override, dict):
            raise ValueError("expected a JSON object")
    except (ValueError, TypeError) as exc:
        logger.warning("Invalid ML_DAMAGE_CLASS_MAP (%s); using defaults", exc)
        return class_map
    for key, value in override.items():
        class_map[_normalize_class_name(key)] = _normalize_class_name(value)
    return class_map


def _uploads_root() -> str:
    """Shared uploads dir; mirrors get_uploads_root() in src/api/process.py."""
    configured = os.getenv("UPLOADS_ROOT", "").strip()
    if configured:
        return os.path.abspath(configured)
    backend_root = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "..")
    return os.path.abspath(os.path.join(backend_root, "backend", "uploads"))


class DamageDetectionModel:
    """
    Wraps a pre-loaded ultralytics detection/segmentation model (from
    ModelRegistry) and converts its predictions into pipeline damage locations.
    """

    def __init__(self, model: Any, model_name: str = "", class_map: Optional[Dict[str, str]] = None):
        self.model = model
        self.model_name = model_name or getattr(model, "ckpt_path", "") or "damage-model"
        self.class_map = class_map or load_class_map()
        self._unmapped_warned: set = set()

    def detect_sync(self, frame_paths: List[str], inspection_id: Optional[str] = None) -> Dict[str, Any]:
        """Run inference on the given frames and return the full damage dict."""
        result = self._empty_result()
        if not frame_paths:
            return result

        try:
            predictions = self.model(
                frame_paths,
                conf=MODEL_CONFIDENCE,
                iou=MODEL_IOU,
                imgsz=MODEL_IMGSZ,
                verbose=False,
            )
        except TypeError as exc:
            # Stub/legacy models without ultralytics kwargs (used in tests)
            # raise "unexpected keyword argument"; a genuine TypeError from
            # inside inference must NOT be silently retried without tuning.
            if "unexpected keyword" not in str(exc):
                return self._failure_result(exc)
            try:
                predictions = self.model(frame_paths)
            except Exception as retry_exc:
                return self._failure_result(retry_exc)
        except Exception as exc:
            return self._failure_result(exc)

        snapshots_dir = self._snapshots_dir(inspection_id)
        locations: List[Dict[str, Any]] = []
        for frame_path, prediction in zip(frame_paths, predictions or []):
            try:
                locations.extend(self._locations_from_prediction(frame_path, prediction, snapshots_dir, len(locations)))
            except Exception as exc:
                logger.warning("Failed to parse damage predictions for %s: %s", frame_path, exc)

        locations.sort(key=lambda loc: loc.get("confidence") or 0.0, reverse=True)
        return self._aggregate(locations)

    # ---- prediction parsing -------------------------------------------------

    def _locations_from_prediction(
        self,
        frame_path: str,
        prediction: Any,
        snapshots_dir: Optional[str],
        counter_start: int,
    ) -> List[Dict[str, Any]]:
        boxes = getattr(prediction, "boxes", None)
        if boxes is None:
            return []
        names = getattr(prediction, "names", None) or getattr(self.model, "names", None) or {}
        masks = getattr(prediction, "masks", None)
        polygons = getattr(masks, "xyn", None) if masks is not None else None

        shape = getattr(prediction, "orig_shape", None)
        frame_h = int(shape[0]) if shape else None
        frame_w = int(shape[1]) if shape else None

        locations: List[Dict[str, Any]] = []
        for index, box in enumerate(boxes):
            try:
                class_id = int(box.cls[0])
                confidence = float(box.conf[0])
                x1, y1, x2, y2 = (float(v) for v in box.xyxy[0])
            except Exception:
                continue

            class_name = _normalize_class_name(names.get(class_id, class_id) if isinstance(names, dict) else class_id)
            damage_type = self.class_map.get(class_name)
            if damage_type is None:
                if class_name not in self._unmapped_warned:
                    self._unmapped_warned.add(class_name)
                    logger.warning(
                        "Damage model class %r has no taxonomy mapping; ignoring "
                        "(extend ML_DAMAGE_CLASS_MAP to include it)", class_name,
                    )
                continue

            bbox = [int(round(x1)), int(round(y1)), int(round(x2)), int(round(y2))]
            if bbox[2] - bbox[0] < 2 or bbox[3] - bbox[1] < 2:
                continue

            area_fraction = 0.0
            if frame_w and frame_h:
                area_fraction = ((bbox[2] - bbox[0]) * (bbox[3] - bbox[1])) / float(frame_w * frame_h)

            location: Dict[str, Any] = {
                "type": damage_type,
                "confidence": round(confidence, 4),
                "severity": self._severity(confidence, area_fraction),
                "frame": frame_path,
                "bbox": bbox,
                "source": "detector",
                "detector_class": class_name,
            }
            if frame_w and frame_h:
                location["frame_width"] = frame_w
                location["frame_height"] = frame_h

            polygon = self._polygon_at(polygons, index)
            if polygon:
                location["mask"] = polygon

            snapshot = self._save_snapshot(frame_path, bbox, damage_type, snapshots_dir, counter_start + len(locations) + 1)
            if snapshot:
                location["snapshot"] = snapshot

            locations.append(location)
        return locations

    @staticmethod
    def _polygon_at(polygons: Any, index: int) -> Optional[List[List[float]]]:
        """Normalized mask polygon [[x, y], ...] for box `index`, if present."""
        if polygons is None:
            return None
        try:
            polygon = polygons[index]
        except (IndexError, TypeError):
            return None
        try:
            points = [[round(float(x), 4), round(float(y), 4)] for x, y in polygon]
        except (TypeError, ValueError):
            return None
        if len(points) < 3:
            return None
        if len(points) > _MAX_MASK_POINTS:
            stride = (len(points) + _MAX_MASK_POINTS - 1) // _MAX_MASK_POINTS
            points = points[::stride]
        return points

    @staticmethod
    def _severity(confidence: float, area_fraction: float) -> str:
        if confidence >= 0.80 or area_fraction >= 0.08:
            return "high"
        if confidence >= 0.55 or area_fraction >= 0.02:
            return "medium"
        return "low"

    # ---- snapshots ----------------------------------------------------------

    @staticmethod
    def _snapshots_dir(inspection_id: Optional[str]) -> Optional[str]:
        if not inspection_id:
            return None
        snapshots_dir = os.path.join(_uploads_root(), "frames", str(inspection_id), "damage_snapshots")
        try:
            os.makedirs(snapshots_dir, exist_ok=True)
        except OSError as exc:
            logger.warning("Could not create detector snapshot dir %s: %s", snapshots_dir, exc)
            return None
        return snapshots_dir

    @staticmethod
    def _save_snapshot(
        frame_path: str,
        bbox: List[int],
        damage_type: str,
        snapshots_dir: Optional[str],
        counter: int,
    ) -> Optional[str]:
        if not snapshots_dir:
            return None
        import cv2  # local import; cv2 is already an ML-service dependency

        image = cv2.imread(frame_path)
        if image is None:
            return None
        h, w = image.shape[:2]
        pad = 24
        x1, y1, x2, y2 = bbox
        crop = image[max(0, y1 - pad):min(h, y2 + pad), max(0, x1 - pad):min(w, x2 + pad)]
        if crop.size == 0:
            return None
        out_full = os.path.join(snapshots_dir, f"detector_{damage_type}_{counter:03d}.jpg")
        try:
            if cv2.imwrite(out_full, crop):
                rel = os.path.relpath(out_full, _uploads_root())
                return rel.replace("\\", "/")
        except Exception as exc:
            logger.debug("Failed to write detector snapshot %s: %s", out_full, exc)
        return None

    # ---- aggregation --------------------------------------------------------

    def _aggregate(self, locations: List[Dict[str, Any]]) -> Dict[str, Any]:
        result = self._empty_result()
        result["locations"] = locations

        for loc in locations:
            category = _TYPE_TO_CATEGORY.get(loc["type"])
            if category:
                result[category]["count"] += 1
                result[category]["detected"] = True

        total = len(locations)
        confidences = [loc["confidence"] for loc in locations if loc.get("confidence") is not None]
        avg_confidence = (sum(confidences) / len(confidences)) if confidences else 0.0

        if total == 0:
            severity = "low"
        elif any(loc.get("severity") == "high" for loc in locations) or total > 5:
            severity = "high"
        elif total > 2 or avg_confidence >= 0.6:
            severity = "medium"
        else:
            severity = "low"

        result["severity"] = severity
        result["total_count"] = total
        result["average_confidence"] = float(round(avg_confidence, 3))
        return result

    def _failure_result(self, exc: Exception) -> Dict[str, Any]:
        """Empty result that surfaces an inference failure instead of masking
        it as a clean zero-findings run. The damage stage still degrades
        gracefully to VLM-only, but the pipeline audit and frontend can see
        ``detector.available == False`` plus the error."""
        logger.error("Damage model inference failed: %s", exc, exc_info=True)
        result = self._empty_result()
        result["detector"] = {
            "available": False,
            "model": os.path.basename(str(self.model_name)),
            "error": str(exc),
        }
        return result

    def _empty_result(self) -> Dict[str, Any]:
        """Zeroed damage dict matching the DamageDetector contract."""
        result: Dict[str, Any] = {cat: {"count": 0, "detected": False} for cat in _CATEGORIES}
        result.update({
            "severity": "low",
            "total_count": 0,
            "average_confidence": 0.0,
            "confidence_threshold": MODEL_CONFIDENCE,
            "locations": [],
            "detector": {
                "available": True,
                "model": os.path.basename(str(self.model_name)),
            },
        })
        return result
