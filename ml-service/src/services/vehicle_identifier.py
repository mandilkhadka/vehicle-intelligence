"""
Vehicle identification service
Identifies vehicle type, brand, and color using YOLOv8 + CLIP zero-shot.

Accuracy improvements over the original implementation:
1. Crops each frame to the YOLO vehicle bbox before passing to CLIP — removes
   irrelevant background that hurts zero-shot text/image alignment.
2. Selects the N frames with the largest vehicle bboxes (the vehicle fills
   the frame) instead of just taking the first three.
3. Uses precomputed prompt-ensemble text embeddings from ModelRegistry, so
   per-request work is just one CLIP image-encode + a small matmul.
4. Aggregates at the embedding level (mean-pool L2-normalized image
   embeddings) rather than averaging softmax outputs.
5. Applies a confidence floor — returns "Unknown" instead of
   confidently picking the closest of 20 fixed brands.
"""

import asyncio
import logging
import os
from typing import Dict, Any, List, Optional, Tuple
from ultralytics import YOLO
from PIL import Image
import torch
import cv2
import numpy as np
from collections import Counter

from src.services.model_registry import VEHICLE_BRANDS, BRAND_PROMPT_TEMPLATES

logger = logging.getLogger(__name__)


# YOLO COCO class IDs we treat as "the vehicle" for cropping.
# 2=car, 3=motorcycle, 5=bus, 7=truck.
_VEHICLE_COCO_CLASSES = {2, 3, 5, 7}

# How many frames (with the largest vehicle bboxes) we feed into CLIP.
_TOP_N_FRAMES_FOR_CLIP = 8

# Padding ratio applied around the YOLO bbox before cropping for CLIP, so we
# keep a bit of context (grille, headlights) without picking up the whole scene.
_CROP_PADDING_RATIO = 0.10

# If the top brand's softmax probability is below this, we return "Unknown"
# instead of guessing among the 20 brands.
_BRAND_CONFIDENCE_FLOOR = 0.25


class VehicleIdentifier:
    """Identifies vehicle type, brand, and color from extracted frames."""

    def __init__(
        self,
        yolo_model: Optional[YOLO] = None,
        clip_model=None,
        clip_processor=None,
        brand_text_embeddings: Optional[torch.Tensor] = None,
        brand_names: Optional[List[str]] = None,
    ):
        """
        Initialize vehicle identifier with models.

        Args:
            yolo_model: Pre-loaded YOLOv8 model (from ModelRegistry).
            clip_model: Pre-loaded CLIP model (from ModelRegistry).
            clip_processor: Pre-loaded CLIP processor (from ModelRegistry).
            brand_text_embeddings: Pre-computed L2-normalized prompt-ensemble text
                embeddings, shape [num_brands, embed_dim]. If None, we encode
                on-the-fly per request (slower).
            brand_names: Brand list aligned with brand_text_embeddings rows.
        """
        # YOLO
        if yolo_model is not None:
            logger.info("VehicleIdentifier: Using injected YOLOv8 model")
            self.yolo_model = yolo_model
        else:
            logger.warning("VehicleIdentifier: Loading YOLOv8 model internally (consider using ModelRegistry)")
            self.yolo_model = YOLO("yolov8n.pt")

        # CLIP
        if clip_model is not None and clip_processor is not None:
            logger.info("VehicleIdentifier: Using injected CLIP model and processor")
            self.clip_model = clip_model
            self.clip_processor = clip_processor
        else:
            logger.warning("VehicleIdentifier: Loading CLIP models internally (consider using ModelRegistry)")
            from transformers import CLIPProcessor, CLIPModel
            os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
            self.clip_model = CLIPModel.from_pretrained(
                "openai/clip-vit-base-patch32", local_files_only=False, resume_download=True
            )
            self.clip_processor = CLIPProcessor.from_pretrained(
                "openai/clip-vit-base-patch32", local_files_only=False, resume_download=True
            )

        # Brand prompts / cached text embeddings
        self.brand_names = list(brand_names) if brand_names else list(VEHICLE_BRANDS)
        self.brand_text_embeddings = brand_text_embeddings  # may be None — fallback path handles it

        self.vehicle_types = ["car", "bike", "motorcycle", "truck", "suv"]

    # ------------------------------------------------------------------ #
    # Public API                                                         #
    # ------------------------------------------------------------------ #

    async def identify(self, frame_paths: List[str]) -> Dict[str, Any]:
        """Identify vehicle from frames. Returns dict with type/brand/model/color/confidence."""
        return await asyncio.to_thread(self._identify_sync, frame_paths)

    # ------------------------------------------------------------------ #
    # Pipeline                                                           #
    # ------------------------------------------------------------------ #

    def _identify_sync(self, frame_paths: List[str]) -> Dict[str, Any]:
        """Sync identification: cache YOLO once, then derive type/brand/color."""
        sample_frames = frame_paths[:5] if len(frame_paths) > 5 else frame_paths

        # Cache YOLO results once per frame; reused by type/color/brand-cropping.
        logger.info(f"VehicleIdentifier: Caching YOLO results for {len(sample_frames)} frames")
        yolo_cache: Dict[str, Any] = {}
        for frame_path in sample_frames:
            try:
                yolo_cache[frame_path] = self.yolo_model(frame_path)
            except Exception as e:
                logger.warning(f"YOLO inference failed for {frame_path}: {e}")
                yolo_cache[frame_path] = None

        vehicle_type = self._detect_vehicle_type_cached(sample_frames[0], yolo_cache)
        brand, model, confidence = self._identify_brand(sample_frames, yolo_cache)
        color = self._detect_vehicle_color_cached(sample_frames, yolo_cache)

        return {
            "type": vehicle_type,
            "brand": brand,
            "model": model,
            "color": color,
            "confidence": confidence,
        }

    # ------------------------------------------------------------------ #
    # Type detection (YOLO)                                              #
    # ------------------------------------------------------------------ #

    def _detect_vehicle_type_cached(self, frame_path: str, yolo_cache: Dict[str, Any]) -> str:
        """Detect vehicle type using cached YOLO results."""
        try:
            results = yolo_cache.get(frame_path)
            if results is None:
                return "car"

            # YOLO COCO classes: 2=car, 3=motorcycle, 7=truck
            vehicle_classes = {2: "car", 3: "bike", 7: "truck"}
            for result in results:
                boxes = result.boxes
                if boxes is not None:
                    for box in boxes:
                        class_id = int(box.cls[0])
                        if class_id in vehicle_classes:
                            return vehicle_classes[class_id]
            return "car"
        except Exception as e:
            logger.warning(f"Vehicle type detection error: {e}")
            return "car"

    # ------------------------------------------------------------------ #
    # Color detection (HSV over YOLO crop)                               #
    # ------------------------------------------------------------------ #

    def _detect_vehicle_color_cached(self, frame_paths: List[str], yolo_cache: Dict[str, Any]) -> str:
        """Detect vehicle color from frames using cached YOLO results."""
        try:
            color_ranges = {
                "White": ([0, 0, 200], [180, 30, 255]),
                "Black": ([0, 0, 0], [180, 255, 50]),
                "Silver": ([0, 0, 150], [180, 30, 200]),
                "Gray": ([0, 0, 50], [180, 30, 150]),
                "Grey": ([0, 0, 50], [180, 30, 150]),
                "Red": ([0, 100, 50], [10, 255, 255]),
                "Blue": ([100, 100, 50], [130, 255, 255]),
                "Green": ([40, 100, 50], [80, 255, 255]),
                "Brown": ([10, 100, 20], [25, 255, 150]),
                "Beige": ([20, 30, 150], [40, 100, 255]),
                "Gold": ([20, 100, 100], [30, 255, 255]),
                "Yellow": ([20, 100, 100], [40, 255, 255]),
                "Orange": ([10, 100, 100], [25, 255, 255]),
                "Purple": ([130, 100, 50], [160, 255, 255]),
            }

            detected_colors = []
            for frame_path in frame_paths[:3]:
                try:
                    image = cv2.imread(frame_path)
                    if image is None:
                        continue

                    vehicle_box = self._largest_vehicle_box(yolo_cache.get(frame_path))
                    if vehicle_box is None:
                        h, w = image.shape[:2]
                        vehicle_box = (w // 4, h // 4, 3 * w // 4, 3 * h // 4)

                    x1, y1, x2, y2 = vehicle_box
                    vehicle_region = image[y1:y2, x1:x2]
                    if vehicle_region.size == 0:
                        continue

                    hsv = cv2.cvtColor(vehicle_region, cv2.COLOR_BGR2HSV)
                    h_center, w_center = hsv.shape[0] // 2, hsv.shape[1] // 2
                    h_margin, w_margin = hsv.shape[0] // 4, hsv.shape[1] // 4
                    center_region = hsv[
                        h_center - h_margin: h_center + h_margin,
                        w_center - w_margin: w_center + w_margin,
                    ]
                    if center_region.size == 0:
                        center_region = hsv

                    # Keep as a (H, W, 3) uint8 image so cv2.inRange is happy.
                    # (The previous .reshape(-1, 3) made cv2.inRange reject the bounds
                    # because of dtype/shape mismatch — the masks always errored out.)
                    pixels = center_region
                    color_counts = {}
                    for color_name, (lower, upper) in color_ranges.items():
                        if color_name == "Red":
                            mask1 = cv2.inRange(
                                pixels,
                                np.array([0, 100, 50], dtype=np.uint8),
                                np.array([10, 255, 255], dtype=np.uint8),
                            )
                            mask2 = cv2.inRange(
                                pixels,
                                np.array([170, 100, 50], dtype=np.uint8),
                                np.array([180, 255, 255], dtype=np.uint8),
                            )
                            mask = mask1 | mask2
                        else:
                            mask = cv2.inRange(
                                pixels,
                                np.array(lower, dtype=np.uint8),
                                np.array(upper, dtype=np.uint8),
                            )
                        count = int(np.sum(mask > 0))
                        if count > 0:
                            color_counts[color_name] = count

                    if color_counts:
                        detected_colors.append(max(color_counts, key=color_counts.get))
                except Exception as e:
                    logger.warning(f"Color detection error for {frame_path}: {e}")
                    continue

            if detected_colors:
                return Counter(detected_colors).most_common(1)[0][0]
            return "Unknown"
        except Exception as e:
            logger.warning(f"Vehicle color detection error: {e}")
            return "Unknown"

    # ------------------------------------------------------------------ #
    # Brand identification (CLIP zero-shot, embedding-level)             #
    # ------------------------------------------------------------------ #

    def _largest_vehicle_box(self, results) -> Optional[Tuple[int, int, int, int]]:
        """Return the largest vehicle bbox (x1,y1,x2,y2) from YOLO results, or None."""
        if results is None:
            return None
        best_area = 0
        best_box: Optional[Tuple[int, int, int, int]] = None
        for result in results:
            boxes = result.boxes
            if boxes is None:
                continue
            for box in boxes:
                class_id = int(box.cls[0])
                if class_id not in _VEHICLE_COCO_CLASSES:
                    continue
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                area = max(0, int(x2) - int(x1)) * max(0, int(y2) - int(y1))
                if area > best_area:
                    best_area = area
                    best_box = (int(x1), int(y1), int(x2), int(y2))
        return best_box

    def _crop_with_padding(
        self, frame_path: str, box: Tuple[int, int, int, int]
    ) -> Optional[Image.Image]:
        """Open frame, crop to box with padding, return as PIL.Image (RGB)."""
        image = cv2.imread(frame_path)
        if image is None:
            return None
        h, w = image.shape[:2]
        x1, y1, x2, y2 = box
        bw = x2 - x1
        bh = y2 - y1
        if bw <= 0 or bh <= 0:
            return None
        pad_x = int(bw * _CROP_PADDING_RATIO)
        pad_y = int(bh * _CROP_PADDING_RATIO)
        x1p = max(0, x1 - pad_x)
        y1p = max(0, y1 - pad_y)
        x2p = min(w, x2 + pad_x)
        y2p = min(h, y2 + pad_y)
        crop_bgr = image[y1p:y2p, x1p:x2p]
        if crop_bgr.size == 0:
            return None
        crop_rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
        return Image.fromarray(crop_rgb)

    def _select_best_frames_for_clip(
        self, frame_paths: List[str], yolo_cache: Dict[str, Any]
    ) -> List[Tuple[str, Tuple[int, int, int, int]]]:
        """
        Score each frame by its largest vehicle-bbox area; return the top N
        as (frame_path, bbox) pairs. Frames with no vehicle detection are
        included only as a last resort using a center crop.
        """
        scored: List[Tuple[int, str, Tuple[int, int, int, int]]] = []
        fallback: List[str] = []

        for frame_path in frame_paths:
            box = self._largest_vehicle_box(yolo_cache.get(frame_path))
            if box is None:
                fallback.append(frame_path)
                continue
            x1, y1, x2, y2 = box
            area = max(0, x2 - x1) * max(0, y2 - y1)
            scored.append((area, frame_path, box))

        scored.sort(key=lambda t: t[0], reverse=True)
        selected = [(path, box) for _, path, box in scored[:_TOP_N_FRAMES_FOR_CLIP]]

        if not selected:
            # No YOLO detections at all — fall back to center crops on first few frames.
            for path in fallback[:_TOP_N_FRAMES_FOR_CLIP]:
                img = cv2.imread(path)
                if img is None:
                    continue
                h, w = img.shape[:2]
                box = (w // 4, h // 4, 3 * w // 4, 3 * h // 4)
                selected.append((path, box))

        return selected

    def _ensure_brand_text_embeddings(self) -> torch.Tensor:
        """Return cached brand text embeddings, computing on the fly if missing."""
        if self.brand_text_embeddings is not None:
            return self.brand_text_embeddings

        logger.warning(
            "VehicleIdentifier: brand_text_embeddings not provided — encoding on-the-fly. "
            "Pass them from ModelRegistry for best performance."
        )
        per_brand = []
        with torch.no_grad():
            for brand in self.brand_names:
                prompts = [tpl.format(brand=brand) for tpl in BRAND_PROMPT_TEMPLATES]
                inputs = self.clip_processor(
                    text=prompts, return_tensors="pt", padding=True, truncation=True
                )
                text_features = self.clip_model.get_text_features(**inputs)
                text_features = text_features / text_features.norm(dim=-1, keepdim=True)
                emb = text_features.mean(dim=0)
                emb = emb / emb.norm()
                per_brand.append(emb)
        self.brand_text_embeddings = torch.stack(per_brand, dim=0)
        return self.brand_text_embeddings

    def _identify_brand(
        self, frame_paths: List[str], yolo_cache: Dict[str, Any]
    ) -> Tuple[str, str, float]:
        """
        Identify brand using CLIP zero-shot:
          1) Pick best frames + their YOLO crops.
          2) Encode crops once with CLIP image encoder, L2-normalize, mean-pool.
          3) Cosine similarity vs cached brand text embeddings → softmax (T=100).
          4) Apply confidence floor → "Unknown" if below threshold.
        Returns (brand, model, confidence). model is always "" (CLIP can't do
        fine-grained model ID without a fine-tuned head).
        """
        try:
            crops_with_paths = self._select_best_frames_for_clip(frame_paths, yolo_cache)
            if not crops_with_paths:
                logger.warning("Brand ID: no usable frames")
                return "Unknown", "", 0.0

            crops: List[Image.Image] = []
            for path, box in crops_with_paths:
                crop = self._crop_with_padding(path, box)
                if crop is not None:
                    crops.append(crop)

            if not crops:
                logger.warning("Brand ID: no usable crops after cropping")
                return "Unknown", "", 0.0

            text_embeddings = self._ensure_brand_text_embeddings()

            with torch.no_grad():
                image_inputs = self.clip_processor(images=crops, return_tensors="pt")
                image_features = self.clip_model.get_image_features(**image_inputs)
                # L2-normalize each frame, then mean-pool, then re-normalize.
                image_features = image_features / image_features.norm(dim=-1, keepdim=True)
                pooled = image_features.mean(dim=0)
                pooled = pooled / pooled.norm()

                # Cosine similarity (both sides L2-normalized) vs brand embeddings.
                # Multiply by CLIP's logit_scale-ish temperature (~100) before softmax
                # so the distribution has the right sharpness — matches CLIP's training.
                sims = pooled @ text_embeddings.T  # shape [num_brands]
                logits = sims * 100.0
                probs = torch.softmax(logits, dim=-1)

                top_prob, top_idx = torch.max(probs, dim=-1)
                confidence = float(top_prob.item())
                brand_idx = int(top_idx.item())

            if confidence < _BRAND_CONFIDENCE_FLOOR:
                logger.info(
                    f"Brand ID: top brand '{self.brand_names[brand_idx]}' below confidence "
                    f"floor ({confidence:.3f} < {_BRAND_CONFIDENCE_FLOOR}) — returning Unknown"
                )
                return "Unknown", "", confidence

            best_brand = self.brand_names[brand_idx]
            logger.info(
                f"Brand ID: {best_brand} (confidence={confidence:.3f}, "
                f"frames_used={len(crops)})"
            )
            # CLIP zero-shot can't reliably name a specific model — leave blank.
            return best_brand, "", confidence

        except Exception as e:
            logger.warning(f"Brand identification error: {e}", exc_info=True)
            return "Unknown", "", 0.0
