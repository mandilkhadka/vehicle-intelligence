"""
Vehicle frame organization service.

Scores extracted walkaround frames and selects representative angle/dashboard
shots before downstream OCR and VLM inspection.
"""

import asyncio
import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image
from ultralytics import YOLO

from src.utils.image_quality import enhance_image_for_analysis, write_jpeg

logger = logging.getLogger(__name__)


EXTERIOR_VIEWS: Tuple[str, ...] = (
    "front",
    "front-left",
    "left",
    "rear-left",
    "rear",
    "rear-right",
    "right",
    "front-right",
)

DETAIL_VIEWS: Tuple[str, ...] = ("wheels", "trunk", "engine-bay")
SPECIAL_VIEWS: Tuple[str, ...] = ("interior", "dashboard", "odometer", *DETAIL_VIEWS)
REVIEW_REQUIRED_VIEWS: Tuple[str, ...] = (
    "front",
    "front-left",
    "left",
    "rear-left",
    "rear",
    "rear-right",
    "right",
    "interior",
    "dashboard",
    "wheels",
    "trunk",
    "engine-bay",
)

VIEW_PROMPTS: Dict[str, List[str]] = {
    "front": [
        "front view of a vehicle",
        "vehicle grille headlights front bumper",
        "straight on front angle car",
    ],
    "front-left": [
        "front left three quarter view of a vehicle",
        "front driver side corner car angle",
        "vehicle front and left side visible",
    ],
    "left": [
        "left side profile of a vehicle",
        "driver side full side view car",
        "vehicle side doors and wheels profile",
    ],
    "rear-left": [
        "rear left three quarter view of a vehicle",
        "vehicle rear and left side visible",
        "back driver side corner car angle",
    ],
    "rear": [
        "rear view of a vehicle",
        "vehicle trunk tail lights rear bumper",
        "straight on back of car",
    ],
    "rear-right": [
        "rear right three quarter view of a vehicle",
        "vehicle rear and right side visible",
        "back passenger side corner car angle",
    ],
    "right": [
        "right side profile of a vehicle",
        "passenger side full side view car",
        "vehicle right side doors and wheels profile",
    ],
    "front-right": [
        "front right three quarter view of a vehicle",
        "front passenger side corner car angle",
        "vehicle front and right side visible",
    ],
    "interior": [
        "vehicle interior cabin seats steering wheel",
        "inside of a car cabin",
        "car interior dashboard and seats",
    ],
    "dashboard": [
        "vehicle dashboard instrument cluster",
        "car dashboard gauges steering wheel",
        "speedometer cluster inside vehicle",
    ],
    "odometer": [
        "close up odometer reading on dashboard",
        "digital odometer mileage display",
        "instrument cluster showing kilometers",
    ],
    "wheels": [
        "close view of vehicle wheels and tires",
        "car wheel rim tire sidewall inspection",
        "vehicle alloy wheel and tire condition",
    ],
    "trunk": [
        "open vehicle trunk cargo area",
        "rear hatch trunk storage compartment",
        "car boot interior inspection",
    ],
    "engine-bay": [
        "open hood engine bay inspection",
        "vehicle engine compartment",
        "car engine bay under bonnet",
    ],
}

_VEHICLE_COCO_CLASSES = {2, 3, 5, 7}
_MAX_ORGANIZER_FRAMES = 96
_MIN_EXTERIOR_VEHICLE_RATIO = 0.04
_HIGH_CONFIDENCE_VIEW_SCORE = 0.45
_HIGH_CONFIDENCE_CLIP_SCORE = 0.12
_MIN_EXTERIOR_CLIP_EVIDENCE_SCORE = 0.08
_HIGH_CONFIDENCE_DASHBOARD_SCORE = 0.50
_HIGH_CONFIDENCE_TEMPORAL_SCORE = 0.80
_HIGH_CONFIDENCE_VEHICLE_RATIO = 0.25
_EXTERIOR_TEMPORAL_WEIGHT = 0.42
_EXTERIOR_TEMPORAL_SIGMA = 0.14
_MIN_EXTERIOR_TEMPORAL_FIT = 0.18
_STRONG_EXTERIOR_CLIP_SCORE = 0.24
_DASHBOARD_LIKE_REJECTION_SCORE = 0.58
_INTERIOR_LIKE_REJECTION_SCORE = 0.32
_MIN_DASHBOARD_CANDIDATE_SCORE = 0.45
_DASHBOARD_EXTERIOR_REJECTION_VEHICLE_RATIO = 0.35
_DASHBOARD_EXTERIOR_REJECTION_SCORE = 0.45
_MIN_DETAIL_VIEW_CLIP_SCORE = 0.28
_MIN_DETAIL_VIEW_SCORE = 0.34
_DETAIL_VIEW_DOMINANCE_MARGIN = 0.08


@dataclass
class FrameCandidate:
    """Internal score bundle for one extracted frame."""

    index: int
    path: str
    blur_score: float
    brightness: float
    contrast: float
    quality_score: float
    vehicle_box: Optional[Tuple[int, int, int, int]]
    vehicle_ratio: float
    heuristic_dashboard_score: float
    view_scores: Dict[str, float]
    metadata: Dict[str, Any] = field(default_factory=dict)


class VehicleFrameOrganizer:
    """
    Selects the best representative frames for key vehicle views and odometer OCR.

    CLIP is used for semantic view scoring when available. If CLIP cannot run, the
    service falls back to deterministic temporal buckets plus image-quality and
    dashboard heuristics so the pipeline still returns organized metadata.
    """

    def __init__(self, yolo_model: Optional[YOLO] = None, clip_model=None, clip_processor=None):
        self.yolo_model = yolo_model
        self.clip_model = clip_model
        self.clip_processor = clip_processor
        self._view_text_embeddings = None
        self._view_names: List[str] = list(VIEW_PROMPTS.keys())

    async def organize(
        self,
        frame_paths: List[str],
        inspection_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(self._organize_sync, frame_paths, inspection_id)

    def _organize_sync(
        self,
        frame_paths: List[str],
        inspection_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not frame_paths:
            return self._empty_result()

        selected_paths = self._limit_frames(frame_paths, _MAX_ORGANIZER_FRAMES)
        frame_metadata = self._load_frame_metadata(frame_paths)
        extraction_metadata = self._load_extraction_metadata(frame_paths)
        candidates = self._score_frames(selected_paths, frame_metadata)
        if not candidates:
            return self._empty_result()

        angle_shots = self._select_angle_shots(candidates)
        dashboard_candidates = self._select_dashboard_candidates(candidates)

        organized_dir = self._organized_output_dir(frame_paths, inspection_id)
        if organized_dir:
            angle_shots = self._copy_angle_shots(angle_shots, organized_dir)
            dashboard_candidates = self._copy_dashboard_candidates(dashboard_candidates, organized_dir)

        representative_frames = self._representative_frames(angle_shots, dashboard_candidates)
        coverage = self._coverage(angle_shots)

        return {
            "angle_shots": angle_shots,
            "dashboard_candidates": dashboard_candidates,
            "representative_frames": representative_frames,
            "coverage": coverage,
            "extraction_metadata": extraction_metadata,
            "frames_analyzed": len(selected_paths),
            "frames_total": len(frame_paths),
            "method": "clip_yolo_quality" if self._clip_available() else "heuristic_temporal_quality",
        }

    def _score_frames(self, frame_paths: List[str], frame_metadata: Optional[Dict[str, Dict[str, Any]]] = None) -> List[FrameCandidate]:
        base: List[Dict[str, Any]] = []
        pil_images: List[Image.Image] = []
        pil_indices: List[int] = []
        frame_metadata = frame_metadata or {}

        for index, path in enumerate(frame_paths):
            image = cv2.imread(path)
            if image is None:
                logger.warning("FrameOrganizer: skipping unreadable frame %s", path)
                continue

            blur = self._blur_score(image)
            brightness = float(np.mean(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)))
            contrast = float(np.std(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)))
            quality = self._quality_score(blur, brightness, contrast)
            vehicle_box, vehicle_ratio = self._vehicle_box_and_ratio(image, path)
            dashboard_score = self._dashboard_heuristic(image, vehicle_box, vehicle_ratio)

            base.append({
                "index": index,
                "path": path,
                "blur_score": blur,
                "brightness": brightness,
                "contrast": contrast,
                "quality_score": quality,
                "vehicle_box": vehicle_box,
                "vehicle_ratio": vehicle_ratio,
                "heuristic_dashboard_score": dashboard_score,
                "metadata": frame_metadata.get(str(Path(path).resolve()), {}),
            })

            if self._clip_available():
                try:
                    pil_images.append(Image.open(path).convert("RGB"))
                    pil_indices.append(len(base) - 1)
                except Exception as e:
                    logger.warning("FrameOrganizer: PIL open failed for %s: %s", path, e)

        clip_scores_by_base_index = self._clip_view_scores(pil_images, pil_indices) if pil_images else {}
        candidates: List[FrameCandidate] = []
        for i, item in enumerate(base):
            view_scores = clip_scores_by_base_index.get(i) or self._fallback_view_scores(
                item["index"], len(frame_paths)
            )
            candidates.append(FrameCandidate(view_scores=view_scores, **item))
        return candidates

    def _select_angle_shots(self, candidates: List[FrameCandidate]) -> Dict[str, Dict[str, Any]]:
        angle_shots: Dict[str, Dict[str, Any]] = {}
        used_indices: set[int] = set()

        for view_offset, view in enumerate(EXTERIOR_VIEWS):
            ranked = sorted(
                candidates,
                key=lambda c: self._walkaround_angle_score(c, view, view_offset, len(candidates)),
                reverse=True,
            )
            chosen = None
            for candidate in ranked:
                if candidate.index in used_indices:
                    continue
                if not self._has_exterior_evidence(candidate, len(candidates)):
                    continue
                if not self._has_exterior_view_fit(candidate, view, view_offset, len(candidates)):
                    continue
                chosen = candidate
                break
            if chosen is None:
                continue

            used_indices.add(chosen.index)
            temporal_score = self._temporal_prior(chosen.index, len(candidates), view_offset, len(EXTERIOR_VIEWS))
            angle_shots[view] = self._candidate_payload(
                chosen,
                view,
                self._walkaround_angle_score(chosen, view, view_offset, len(candidates)),
                temporal_score=temporal_score,
            )

        for view_offset, view in enumerate(EXTERIOR_VIEWS):
            if angle_shots.get(view):
                continue
            ranked = sorted(
                candidates,
                key=lambda c: (
                    c.index in used_indices,
                    -self._walkaround_angle_score(c, view, view_offset, len(candidates)),
                ),
            )
            chosen = None
            for candidate in ranked:
                if candidate.index in used_indices:
                    continue
                if self._has_exterior_evidence(candidate, len(candidates)):
                    if not self._has_exterior_view_fit(candidate, view, view_offset, len(candidates)):
                        continue
                    chosen = candidate
                    break
            if chosen is None:
                for candidate in ranked:
                    if self._has_exterior_evidence(candidate, len(candidates)):
                        if not self._has_exterior_view_fit(candidate, view, view_offset, len(candidates)):
                            continue
                        chosen = candidate
                        break
            if chosen is None:
                continue

            used_indices.add(chosen.index)
            temporal_score = self._temporal_prior(chosen.index, len(candidates), view_offset, len(EXTERIOR_VIEWS))
            payload = self._candidate_payload(
                chosen,
                view,
                self._walkaround_angle_score(chosen, view, view_offset, len(candidates)),
                temporal_score=temporal_score,
            )
            payload["candidate_role"] = "fallback_angle"
            angle_shots[view] = payload

        for view in SPECIAL_VIEWS:
            ranked = sorted(
                candidates,
                key=lambda c: self._special_view_score(c, view),
                reverse=True,
            )
            chosen = None
            for candidate in ranked:
                score = self._special_view_score(candidate, view)
                if not self._has_special_view_evidence(candidate, view, score):
                    continue
                chosen = candidate
                break
            if chosen is None:
                continue
            angle_shots[view] = self._candidate_payload(
                chosen, view, self._special_view_score(chosen, view)
            )

        return angle_shots

    def _select_dashboard_candidates(self, candidates: List[FrameCandidate], limit: int = 6) -> List[Dict[str, Any]]:
        ranked = sorted(
            candidates,
            key=lambda c: max(
                self._special_view_score(c, "dashboard"),
                self._special_view_score(c, "odometer"),
            ),
            reverse=True,
        )

        selected: List[Dict[str, Any]] = []
        used: set[int] = set()
        min_score = _MIN_DASHBOARD_CANDIDATE_SCORE if (self._clip_available() or self.yolo_model is not None) else 0.12
        for candidate in ranked:
            if candidate.index in used:
                continue
            dashboard_score = self._special_view_score(candidate, "dashboard")
            odometer_score = self._special_view_score(candidate, "odometer")
            view = "odometer" if odometer_score > dashboard_score else "dashboard"
            score = max(dashboard_score, odometer_score)
            if len(selected) >= limit:
                break
            if score < min_score:
                if selected:
                    break
                continue
            if not self._has_dashboard_candidate_evidence(candidate):
                continue
            payload = self._candidate_payload(candidate, view, score)
            payload["candidate_role"] = "dashboard_candidate"
            selected.append(payload)
            used.add(candidate.index)
        return selected

    def _copy_angle_shots(
        self,
        angle_shots: Dict[str, Dict[str, Any]],
        organized_dir: Path,
    ) -> Dict[str, Dict[str, Any]]:
        for view, payload in angle_shots.items():
            full_path = self._copy_frame(
                payload["frame"],
                organized_dir / f"angle_{view}.jpg",
            )
            payload["organized_path"] = full_path
            payload["inspection_path"] = full_path or payload.get("frame")
            payload["preview_path"] = self._write_preview(
                payload["inspection_path"],
                organized_dir / "previews" / f"angle_{view}.jpg",
            )
        return angle_shots

    def _copy_dashboard_candidates(
        self,
        dashboard_candidates: List[Dict[str, Any]],
        organized_dir: Path,
    ) -> List[Dict[str, Any]]:
        for i, payload in enumerate(dashboard_candidates):
            full_path = self._copy_frame(
                payload["frame"],
                organized_dir / f"dashboard_candidate_{i + 1:02d}.jpg",
            )
            payload["organized_path"] = full_path
            payload["inspection_path"] = full_path or payload.get("frame")
            payload["preview_path"] = self._write_preview(
                payload["inspection_path"],
                organized_dir / "previews" / f"dashboard_candidate_{i + 1:02d}.jpg",
            )
            payload["crop_path"] = self._write_dashboard_crop(
                payload["frame"],
                organized_dir / f"dashboard_candidate_{i + 1:02d}_crop.jpg",
            )
            if payload.get("crop_path"):
                payload["readout_crop_path"] = self._write_odometer_readout_crop(
                    payload["crop_path"],
                    organized_dir / f"dashboard_candidate_{i + 1:02d}_readout.jpg",
                )
        return dashboard_candidates

    @staticmethod
    def _copy_frame(src: str, dest: Path) -> Optional[str]:
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            return str(dest)
        except Exception as e:
            logger.warning("FrameOrganizer: failed to copy %s to %s: %s", src, dest, e)
            return None

    @staticmethod
    def _write_preview(src: Optional[str], dest: Path, max_width: int = 720) -> Optional[str]:
        if not src:
            return None
        try:
            image = cv2.imread(src)
            if image is None:
                return None
            h, w = image.shape[:2]
            preview = image
            if w > max_width:
                scale = max_width / float(w)
                preview = cv2.resize(
                    image,
                    (max_width, max(1, int(round(h * scale)))),
                    interpolation=cv2.INTER_AREA,
                )
            return str(dest) if write_jpeg(dest, preview, 84) else None
        except Exception as e:
            logger.warning("FrameOrganizer: failed to write preview %s: %s", dest, e)
            return None

    @staticmethod
    def _write_dashboard_crop(src: str, dest: Path) -> Optional[str]:
        image = cv2.imread(src)
        if image is None:
            return None
        h, w = image.shape[:2]
        # Keep OCR focused on the instrument cluster behind the steering wheel.
        # The full dashboard frame is still preserved as organized_path for VLM
        # context; crop_path is intentionally tighter to avoid signage/screens.
        x1, y1 = int(w * 0.34), int(h * 0.42)
        x2, y2 = int(w * 0.62), int(h * 0.60)
        crop = image[y1:y2, x1:x2]
        if crop.size == 0:
            return None
        crop = enhance_image_for_analysis(
            crop,
            min_width=900,
            min_height=320,
            denoise=True,
        )
        try:
            return str(dest) if write_jpeg(dest, crop, 98) else None
        except Exception as e:
            logger.warning("FrameOrganizer: failed to write dashboard crop %s: %s", dest, e)
            return None

    @staticmethod
    def _write_odometer_readout_crop(src: str, dest: Path) -> Optional[str]:
        """Write a tighter crop around a likely numeric odometer readout."""
        image = cv2.imread(src)
        if image is None:
            return None
        bbox = VehicleFrameOrganizer._find_readout_bbox(image)
        if bbox is None:
            return None

        x1, y1, x2, y2 = bbox
        h, w = image.shape[:2]
        pad_x = max(8, int((x2 - x1) * 0.35))
        pad_y = max(6, int((y2 - y1) * 0.80))
        x1 = max(0, x1 - pad_x)
        y1 = max(0, y1 - pad_y)
        x2 = min(w, x2 + pad_x)
        y2 = min(h, y2 + pad_y)
        crop = image[y1:y2, x1:x2]
        if crop.size == 0:
            return None
        crop = enhance_image_for_analysis(
            crop,
            min_width=720,
            min_height=180,
            denoise=True,
        )
        try:
            return str(dest) if write_jpeg(dest, crop, 98) else None
        except Exception as e:
            logger.warning("FrameOrganizer: failed to write odometer readout crop %s: %s", dest, e)
            return None

    @staticmethod
    def _find_readout_bbox(image: np.ndarray) -> Optional[Tuple[int, int, int, int]]:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape[:2]
        if h < 20 or w < 40:
            return None

        search_x1, search_x2 = int(w * 0.08), int(w * 0.88)
        search_y1, search_y2 = int(h * 0.22), int(h * 0.88)
        roi = gray[search_y1:search_y2, search_x1:search_x2]
        if roi.size == 0:
            return None

        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(roi)
        bright_threshold = max(145, int(np.percentile(enhanced, 94)))
        dark_threshold = min(110, int(np.percentile(enhanced, 12)))
        masks = [
            cv2.threshold(enhanced, bright_threshold, 255, cv2.THRESH_BINARY)[1],
            cv2.threshold(enhanced, dark_threshold, 255, cv2.THRESH_BINARY_INV)[1],
        ]

        best: Optional[Tuple[float, Tuple[int, int, int, int]]] = None
        for idx, mask in enumerate(masks):
            candidate = VehicleFrameOrganizer._best_textline_bbox(mask, search_x1, search_y1, w, h)
            if candidate is None:
                continue
            score, bbox = candidate
            if idx == 0:
                score += 4.0
            if best is None or score > best[0]:
                best = (score, bbox)

        return best[1] if best else None

    @staticmethod
    def _best_textline_bbox(
        mask: np.ndarray,
        x_offset: int,
        y_offset: int,
        image_width: int,
        image_height: int,
    ) -> Optional[Tuple[float, Tuple[int, int, int, int]]]:
        num_labels, _labels, stats, centroids = cv2.connectedComponentsWithStats(mask, 8)
        boxes: List[Tuple[int, int, int, int, int, float, float]] = []
        min_h = max(5, int(image_height * 0.018))
        max_h = max(min_h + 1, int(image_height * 0.16))
        max_w = max(12, int(image_width * 0.12))
        min_area = max(8, int(image_width * image_height * 0.000015))

        for i in range(1, num_labels):
            x, y, w, h, area = stats[i]
            if area < min_area or h < min_h or h > max_h or w > max_w:
                continue
            aspect = w / max(h, 1)
            fill = area / float(max(w * h, 1))
            if aspect < 0.12 or aspect > 2.4 or fill < 0.12 or fill > 0.92:
                continue
            cx, cy = centroids[i]
            boxes.append((x, y, w, h, area, float(cx), float(cy)))

        if len(boxes) < 4:
            return None

        boxes.sort(key=lambda item: item[6])
        lines: List[List[Tuple[int, int, int, int, int, float, float]]] = []
        for box in boxes:
            cy = box[6]
            matched = False
            for line in lines:
                median_h = float(np.median([item[3] for item in line]))
                median_y = float(np.median([item[6] for item in line]))
                if abs(cy - median_y) <= max(6.0, median_h * 0.85):
                    line.append(box)
                    matched = True
                    break
            if not matched:
                lines.append([box])

        best: Optional[Tuple[float, Tuple[int, int, int, int]]] = None
        for line in lines:
            line.sort(key=lambda item: item[0])
            runs: List[List[Tuple[int, int, int, int, int, float, float]]] = [[]]
            median_h = float(np.median([item[3] for item in line]))
            for box in line:
                if not runs[-1]:
                    runs[-1].append(box)
                    continue
                prev = runs[-1][-1]
                gap = box[0] - (prev[0] + prev[2])
                if gap > max(10.0, median_h * 2.4):
                    runs.append([box])
                else:
                    runs[-1].append(box)

            for run in runs:
                if len(run) < 4 or len(run) > 9:
                    continue
                x1 = min(item[0] for item in run)
                y1 = min(item[1] for item in run)
                x2 = max(item[0] + item[2] for item in run)
                y2 = max(item[1] + item[3] for item in run)
                width = x2 - x1
                height = y2 - y1
                if width < image_width * 0.035 or width > image_width * 0.42:
                    continue
                if height > image_height * 0.18:
                    continue
                avg_h = float(np.mean([item[3] for item in run]))
                score = (len(run) * 2.0) + (width / max(image_width, 1)) + (avg_h / max(image_height, 1))
                bbox = (x1 + x_offset, y1 + y_offset, x2 + x_offset, y2 + y_offset)
                if best is None or score > best[0]:
                    best = (score, bbox)

        return best

    @staticmethod
    def _representative_frames(
        angle_shots: Dict[str, Dict[str, Any]],
        dashboard_candidates: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        reps: List[Dict[str, Any]] = []
        seen: set[str] = set()

        for view in (*EXTERIOR_VIEWS, *SPECIAL_VIEWS):
            payload = angle_shots.get(view)
            if not payload:
                continue
            path = payload.get("organized_path") or payload.get("frame")
            if not path or path in seen:
                continue
            seen.add(path)
            reps.append(VehicleFrameOrganizer._representative_payload(view, path, payload))

        for payload in dashboard_candidates[:3]:
            path = payload.get("organized_path") or payload.get("frame")
            if not path or path in seen:
                continue
            seen.add(path)
            candidate_view = payload.get("view") or "dashboard"
            reps.append(VehicleFrameOrganizer._representative_payload(f"{candidate_view}_candidate", path, payload))

        return reps

    @staticmethod
    def _representative_payload(view: str, path: str, source: Dict[str, Any]) -> Dict[str, Any]:
        payload = {
            "view": view,
            "frame": source.get("inspection_path") or path,
            "inspection_path": source.get("inspection_path") or path,
            "preview_path": source.get("preview_path"),
            "score": source.get("score"),
        }
        for key in (
            "frame_index",
            "extracted_index",
            "source_frame_index",
            "timestamp_seconds",
            "quality_score",
            "vehicle_ratio",
            "dashboard_score",
            "clip_score",
            "temporal_score",
            "high_confidence",
            "semantic_source",
            "candidate_role",
            "organized_path",
            "crop_path",
            "readout_crop_path",
        ):
            if source.get(key) is not None:
                payload[key] = source.get(key)
        return payload

    @staticmethod
    def _coverage(angle_shots: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        required = list(REVIEW_REQUIRED_VIEWS)
        present = [view for view in required if angle_shots.get(view)]
        high_confidence = [
            view
            for view in required
            if angle_shots.get(view) and angle_shots[view].get("high_confidence")
        ]
        missing = [view for view in required if view not in present]
        low_confidence = [view for view in present if view not in high_confidence]
        return {
            "required_views": required,
            "present_views": present,
            "high_confidence_views": high_confidence,
            "low_confidence_views": low_confidence,
            "missing_views": missing,
            "ratio": round(len(present) / len(required), 3) if required else 0.0,
            "high_confidence_ratio": round(len(high_confidence) / len(required), 3) if required else 0.0,
        }

    def _angle_score(self, candidate: FrameCandidate, view: str) -> float:
        semantic = candidate.view_scores.get(view, 0.0)
        vehicle = min(candidate.vehicle_ratio / 0.45, 1.0)
        return (semantic * 0.60) + (candidate.quality_score * 0.25) + (vehicle * 0.15)

    def _has_exterior_evidence(self, candidate: FrameCandidate, total_candidates: int) -> bool:
        if self._is_dashboard_or_interior_like(candidate):
            return False
        if self.yolo_model is not None:
            return candidate.vehicle_ratio >= _MIN_EXTERIOR_VEHICLE_RATIO
        position = candidate.index / max(total_candidates - 1, 1)
        late_dashboard_like = position >= 0.65 and candidate.heuristic_dashboard_score >= 0.55
        return not late_dashboard_like

    def _has_exterior_view_fit(
        self,
        candidate: FrameCandidate,
        view: str,
        view_offset: int,
        total_candidates: int,
    ) -> bool:
        semantic = candidate.view_scores.get(view, 0.0)
        temporal = self._temporal_prior(candidate.index, total_candidates, view_offset, len(EXTERIOR_VIEWS))
        if semantic >= _STRONG_EXTERIOR_CLIP_SCORE and temporal >= 0.08:
            return True
        if temporal >= _MIN_EXTERIOR_TEMPORAL_FIT and semantic >= _MIN_EXTERIOR_CLIP_EVIDENCE_SCORE:
            return True
        return not self._clip_available() and semantic >= 0.50 and temporal >= 0.25

    def _is_dashboard_or_interior_like(self, candidate: FrameCandidate) -> bool:
        exterior_score = max(candidate.view_scores.get(view, 0.0) for view in EXTERIOR_VIEWS)
        dashboard_score = max(
            candidate.view_scores.get("dashboard", 0.0),
            candidate.view_scores.get("odometer", 0.0),
        )
        interior_score = candidate.view_scores.get("interior", 0.0)

        if candidate.heuristic_dashboard_score >= _DASHBOARD_LIKE_REJECTION_SCORE:
            return dashboard_score >= exterior_score or interior_score >= exterior_score * 0.75
        if interior_score >= _INTERIOR_LIKE_REJECTION_SCORE and interior_score > exterior_score:
            return True
        if (
            dashboard_score >= _INTERIOR_LIKE_REJECTION_SCORE
            and candidate.heuristic_dashboard_score >= _DASHBOARD_EXTERIOR_REJECTION_SCORE
            and dashboard_score > exterior_score
        ):
            return True
        return False

    def _has_dashboard_candidate_evidence(self, candidate: FrameCandidate) -> bool:
        if self.yolo_model is None:
            return True
        exterior_dominates = candidate.vehicle_ratio >= _DASHBOARD_EXTERIOR_REJECTION_VEHICLE_RATIO
        weak_dashboard_evidence = candidate.heuristic_dashboard_score < _DASHBOARD_EXTERIOR_REJECTION_SCORE
        return not (exterior_dominates and weak_dashboard_evidence)

    def _has_special_view_evidence(self, candidate: FrameCandidate, view: str, score: float) -> bool:
        if view not in DETAIL_VIEWS:
            return True
        if not self._clip_available():
            return False

        detail_clip_score = candidate.view_scores.get(view, 0.0)
        competing_cabin_score = max(
            candidate.view_scores.get("interior", 0.0),
            candidate.view_scores.get("dashboard", 0.0),
            candidate.view_scores.get("odometer", 0.0),
        )
        if detail_clip_score < _MIN_DETAIL_VIEW_CLIP_SCORE:
            return False
        if score < _MIN_DETAIL_VIEW_SCORE:
            return False
        if competing_cabin_score >= detail_clip_score - _DETAIL_VIEW_DOMINANCE_MARGIN:
            return False
        return True

    def _walkaround_angle_score(
        self,
        candidate: FrameCandidate,
        view: str,
        view_offset: int,
        total_candidates: int,
    ) -> float:
        visual_score = self._angle_score(candidate, view)
        temporal_score = self._temporal_prior(candidate.index, total_candidates, view_offset, len(EXTERIOR_VIEWS))
        return (
            visual_score * (1.0 - _EXTERIOR_TEMPORAL_WEIGHT)
            + temporal_score * _EXTERIOR_TEMPORAL_WEIGHT
        )

    @staticmethod
    def _temporal_prior(
        candidate_index: int,
        total_candidates: int,
        view_offset: int,
        total_views: int,
    ) -> float:
        if total_candidates <= 1 or total_views <= 1:
            return 1.0
        position = candidate_index / max(total_candidates - 1, 1)
        expected = view_offset / max(total_views - 1, 1)
        distance = abs(position - expected)
        score = np.exp(-((distance ** 2) / (2 * (_EXTERIOR_TEMPORAL_SIGMA ** 2))))
        return float(np.clip(score, 0.0, 1.0))

    def _special_view_score(self, candidate: FrameCandidate, view: str) -> float:
        semantic = candidate.view_scores.get(view, 0.0)
        dashboard = candidate.heuristic_dashboard_score
        vehicle_penalty = 1.0 - min(candidate.vehicle_ratio / 0.35, 1.0)
        if view == "dashboard":
            return (semantic * 0.55) + (dashboard * 0.30) + (candidate.quality_score * 0.15)
        if view == "odometer":
            return (semantic * 0.65) + (dashboard * 0.25) + (candidate.quality_score * 0.10)
        return (semantic * 0.70) + (vehicle_penalty * 0.15) + (candidate.quality_score * 0.15)

    def _candidate_payload(
        self,
        candidate: FrameCandidate,
        view: str,
        score: float,
        temporal_score: Optional[float] = None,
    ) -> Dict[str, Any]:
        semantic_source = "clip" if self._clip_available() else "temporal_fallback"
        is_dashboard_like = view in {"dashboard", "odometer"}
        clip_score = candidate.view_scores.get(view, 0.0)
        if semantic_source == "clip":
            if is_dashboard_like:
                high_confidence = (
                    score >= _HIGH_CONFIDENCE_VIEW_SCORE
                    and clip_score >= _HIGH_CONFIDENCE_CLIP_SCORE
                    and candidate.heuristic_dashboard_score >= _HIGH_CONFIDENCE_DASHBOARD_SCORE
                )
            elif view == "interior":
                high_confidence = (
                    score >= _HIGH_CONFIDENCE_VIEW_SCORE
                    and clip_score >= _HIGH_CONFIDENCE_CLIP_SCORE
                )
            else:
                exterior_visual_evidence = (
                    candidate.vehicle_ratio >= _HIGH_CONFIDENCE_VEHICLE_RATIO
                    and temporal_score is not None
                    and temporal_score >= _HIGH_CONFIDENCE_TEMPORAL_SCORE
                    and clip_score >= _MIN_EXTERIOR_CLIP_EVIDENCE_SCORE
                )
                high_confidence = (
                    score >= _HIGH_CONFIDENCE_VIEW_SCORE
                    and (
                        clip_score >= _HIGH_CONFIDENCE_CLIP_SCORE
                        or exterior_visual_evidence
                    )
                    and candidate.vehicle_ratio >= _MIN_EXTERIOR_VEHICLE_RATIO
                    and (temporal_score is None or temporal_score >= 0.25)
                )
        else:
            high_confidence = (
                is_dashboard_like
                and score >= _HIGH_CONFIDENCE_VIEW_SCORE
                and candidate.heuristic_dashboard_score >= _HIGH_CONFIDENCE_DASHBOARD_SCORE
            )
        public_frame_index = candidate.metadata.get("extracted_index", candidate.index)
        payload = {
            "view": view,
            "frame": candidate.path,
            "frame_index": public_frame_index,
            "score": round(float(score), 4),
            "high_confidence": bool(high_confidence),
            "semantic_source": semantic_source,
            "quality_score": round(float(candidate.quality_score), 4),
            "vehicle_ratio": round(float(candidate.vehicle_ratio), 4),
            "vehicle_bbox": list(candidate.vehicle_box) if candidate.vehicle_box else None,
            "dashboard_score": round(float(candidate.heuristic_dashboard_score), 4),
            "clip_score": round(float(clip_score), 4),
        }
        for key in ("extracted_index", "source_frame_index", "timestamp_seconds"):
            if candidate.metadata.get(key) is not None:
                payload[key] = candidate.metadata.get(key)
        if temporal_score is not None:
            payload["temporal_score"] = round(float(temporal_score), 4)
        return payload

    @staticmethod
    def _load_frame_metadata(frame_paths: List[str]) -> Dict[str, Dict[str, Any]]:
        if not frame_paths:
            return {}
        metadata_path = Path(frame_paths[0]).parent / "frame_metadata.json"
        if not metadata_path.exists():
            return {}
        try:
            import json

            data = json.loads(metadata_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("FrameOrganizer: failed to load frame metadata %s: %s", metadata_path, e)
            return {}

        out: Dict[str, Dict[str, Any]] = {}
        for item in data.get("frames") or []:
            if not isinstance(item, dict):
                continue
            path = item.get("path")
            if not path:
                continue
            out[str(Path(path).resolve())] = item
        return out

    @staticmethod
    def _load_extraction_metadata(frame_paths: List[str]) -> Dict[str, Any]:
        if not frame_paths:
            return {}
        metadata_path = Path(frame_paths[0]).parent / "frame_metadata.json"
        if not metadata_path.exists():
            return {}
        try:
            import json

            data = json.loads(metadata_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("FrameOrganizer: failed to load extraction metadata %s: %s", metadata_path, e)
            return {}

        frames = [item for item in data.get("frames") or [] if isinstance(item, dict)]
        timestamps = [
            float(item["timestamp_seconds"])
            for item in frames
            if item.get("timestamp_seconds") is not None
        ]
        video_fps = float(data.get("video_fps") or 0.0)
        total_source_frames = int(data.get("total_source_frames") or 0)
        duration = (
            round(total_source_frames / video_fps, 3)
            if video_fps > 0 and total_source_frames > 0
            else None
        )
        first_timestamp = min(timestamps) if timestamps else None
        last_timestamp = max(timestamps) if timestamps else None
        temporal_coverage_ratio = (
            round(float(last_timestamp) / duration, 4)
            if duration and last_timestamp is not None and duration > 0
            else None
        )

        return {
            "video_fps": video_fps or None,
            "total_source_frames": total_source_frames or None,
            "video_duration_seconds": duration,
            "first_timestamp_seconds": first_timestamp,
            "last_timestamp_seconds": last_timestamp,
            "temporal_coverage_ratio": temporal_coverage_ratio,
            "frames_extracted": data.get("frames_extracted", len(frames)),
            "skipped_blurry": data.get("skipped_blurry"),
            "skipped_duplicate": data.get("skipped_duplicate"),
            "frame_interval": data.get("frame_interval"),
        }

    def _clip_view_scores(
        self,
        images: List[Image.Image],
        pil_indices: List[int],
    ) -> Dict[int, Dict[str, float]]:
        if not self._clip_available():
            return {}

        try:
            import torch

            text_embeddings = self._ensure_view_text_embeddings()
            with torch.no_grad():
                image_inputs = self.clip_processor(images=images, return_tensors="pt")
                image_features = self.clip_model.get_image_features(**image_inputs)
                if hasattr(image_features, "pooler_output"):
                    image_features = image_features.pooler_output
                if isinstance(image_features, (tuple, list)):
                    image_features = image_features[0]
                image_features = image_features / image_features.norm(dim=-1, keepdim=True)
                sims = image_features @ text_embeddings.T
                probs = torch.softmax(sims * 35.0, dim=-1).cpu().numpy()

            scores: Dict[int, Dict[str, float]] = {}
            for row_idx, base_idx in enumerate(pil_indices):
                scores[base_idx] = {
                    view: float(probs[row_idx][view_idx])
                    for view_idx, view in enumerate(self._view_names)
                }
            return scores
        except Exception as e:
            logger.warning("FrameOrganizer: CLIP view scoring failed, using fallback: %s", e)
            return {}

    def _ensure_view_text_embeddings(self):
        if self._view_text_embeddings is not None:
            return self._view_text_embeddings

        if not self._clip_available():
            return None

        import torch

        embeddings = []
        with torch.no_grad():
            for view in self._view_names:
                prompts = VIEW_PROMPTS[view]
                inputs = self.clip_processor(
                    text=prompts,
                    return_tensors="pt",
                    padding=True,
                    truncation=True,
                )
                text_features = self.clip_model.get_text_features(**inputs)
                if hasattr(text_features, "pooler_output"):
                    text_features = text_features.pooler_output
                if isinstance(text_features, (tuple, list)):
                    text_features = text_features[0]
                text_features = text_features / text_features.norm(dim=-1, keepdim=True)
                view_embedding = text_features.mean(dim=0)
                view_embedding = view_embedding / view_embedding.norm()
                embeddings.append(view_embedding)

        self._view_text_embeddings = torch.stack(embeddings, dim=0)
        return self._view_text_embeddings

    def _vehicle_box_and_ratio(
        self,
        image: np.ndarray,
        frame_path: str,
    ) -> Tuple[Optional[Tuple[int, int, int, int]], float]:
        if self.yolo_model is None:
            return None, 0.0
        try:
            results = self.yolo_model(frame_path)
        except Exception as e:
            logger.warning("FrameOrganizer: YOLO failed for %s: %s", frame_path, e)
            return None, 0.0

        best_area = 0
        best_box = None
        for result in results:
            boxes = result.boxes
            if boxes is None:
                continue
            for box in boxes:
                class_id = int(box.cls[0])
                if class_id not in _VEHICLE_COCO_CLASSES:
                    continue
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                x1i, y1i, x2i, y2i = int(x1), int(y1), int(x2), int(y2)
                area = max(0, x2i - x1i) * max(0, y2i - y1i)
                if area > best_area:
                    best_area = area
                    best_box = (x1i, y1i, x2i, y2i)

        h, w = image.shape[:2]
        ratio = best_area / float(max(w * h, 1))
        return best_box, ratio

    @staticmethod
    def _dashboard_heuristic(
        image: np.ndarray,
        vehicle_box: Optional[Tuple[int, int, int, int]],
        vehicle_ratio: float,
    ) -> float:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape[:2]
        center = gray[int(h * 0.20): int(h * 0.72), int(w * 0.18): int(w * 0.82)]
        if center.size == 0:
            center = gray

        dark_ratio = float(np.mean(center < 70))
        bright_ratio = float(np.mean(center > 185))
        edge_density = float(np.mean(cv2.Canny(center, 60, 160) > 0))
        no_large_exterior = 1.0 - min(vehicle_ratio / 0.25, 1.0)
        box_penalty = 0.0 if vehicle_box is None else min(vehicle_ratio / 0.5, 1.0) * 0.2

        score = (
            min(dark_ratio * 1.5, 1.0) * 0.30
            + min(bright_ratio * 2.0, 1.0) * 0.15
            + min(edge_density * 8.0, 1.0) * 0.25
            + no_large_exterior * 0.30
            - box_penalty
        )
        return float(np.clip(score, 0.0, 1.0))

    @staticmethod
    def _blur_score(image: np.ndarray) -> float:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        return float(cv2.Laplacian(gray, cv2.CV_64F).var())

    @staticmethod
    def _quality_score(blur: float, brightness: float, contrast: float) -> float:
        sharpness = min(blur / 250.0, 1.0)
        brightness_score = 1.0 - min(abs(brightness - 128.0) / 128.0, 1.0)
        contrast_score = min(contrast / 70.0, 1.0)
        return float(np.clip((sharpness * 0.45) + (brightness_score * 0.25) + (contrast_score * 0.30), 0.0, 1.0))

    @staticmethod
    def _limit_frames(frame_paths: List[str], max_frames: int) -> List[str]:
        if len(frame_paths) <= max_frames:
            return list(frame_paths)
        step = len(frame_paths) / max_frames
        return [frame_paths[int(i * step)] for i in range(max_frames)]

    @staticmethod
    def _fallback_view_scores(index: int, total: int) -> Dict[str, float]:
        scores = {view: 0.01 for view in VIEW_PROMPTS}
        if total <= 0:
            return scores

        bucket = min(int((index / max(total, 1)) * len(EXTERIOR_VIEWS)), len(EXTERIOR_VIEWS) - 1)
        scores[EXTERIOR_VIEWS[bucket]] = 0.70
        if index >= int(total * 0.75):
            scores["interior"] = 0.20
            scores["dashboard"] = 0.20
            scores["odometer"] = 0.15
        return scores

    def _clip_available(self) -> bool:
        return self.clip_model is not None and self.clip_processor is not None

    @staticmethod
    def _organized_output_dir(frame_paths: List[str], inspection_id: Optional[str]) -> Optional[Path]:
        if not frame_paths:
            return None
        first = Path(frame_paths[0])
        parent = first.parent
        if inspection_id and parent.name != inspection_id:
            parent = parent / inspection_id
        return parent / "organized"

    @staticmethod
    def _empty_result() -> Dict[str, Any]:
        return {
            "angle_shots": {},
            "dashboard_candidates": [],
            "representative_frames": [],
            "coverage": {
                "required_views": list(EXTERIOR_VIEWS) + ["dashboard"],
                "present_views": [],
                "high_confidence_views": [],
                "low_confidence_views": [],
                "missing_views": list(EXTERIOR_VIEWS) + ["dashboard"],
                "ratio": 0.0,
                "high_confidence_ratio": 0.0,
            },
            "extraction_metadata": {},
            "frames_analyzed": 0,
            "frames_total": 0,
            "method": "none",
        }
