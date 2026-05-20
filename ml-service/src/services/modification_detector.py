"""
Local visual modification detector.

Uses CLIP zero-shot prompts over organized walkaround frames to provide
structured stock-vs-modified evidence when the live VLM path is unavailable.
This is intentionally conservative: ambiguous part categories remain unknown.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from PIL import Image

from src.services.model_registry import clip_features_to_tensor

logger = logging.getLogger(__name__)


_STOCK_CONFIDENCE_THRESHOLD = 0.60
_STOCK_MARGIN_THRESHOLD = 0.08
_MODIFIED_CONFIDENCE_THRESHOLD = 0.985
_MODIFIED_MARGIN_THRESHOLD = 0.70
_MAX_IMAGES_PER_PART = 6


@dataclass(frozen=True)
class PartPromptConfig:
    part: str
    views: Sequence[str]
    stock_prompts: Sequence[str]
    modified_prompts: Sequence[str]


PART_PROMPTS: Sequence[PartPromptConfig] = (
    PartPromptConfig(
        part="wheels",
        views=("front-left", "left", "rear-left", "rear-right", "right", "front-right"),
        stock_prompts=(
            "factory stock wheels on a vehicle",
            "original manufacturer wheel rims",
            "standard OEM alloy wheels",
        ),
        modified_prompts=(
            "aftermarket custom wheels on a vehicle",
            "modified large custom rims",
            "non factory aftermarket wheel rims",
        ),
    ),
    PartPromptConfig(
        part="lights",
        views=("front", "front-left", "front-right", "rear", "rear-left", "rear-right"),
        stock_prompts=(
            "factory stock vehicle headlights and tail lights",
            "original manufacturer car lights",
            "standard OEM headlight tail light assembly",
        ),
        modified_prompts=(
            "aftermarket modified vehicle lights",
            "custom tinted headlights or tail lights",
            "non factory LED light modification",
        ),
    ),
    PartPromptConfig(
        part="body",
        views=("front", "front-left", "left", "rear-left", "rear", "rear-right", "right", "front-right"),
        stock_prompts=(
            "factory stock vehicle body panels",
            "standard original car bumper and body",
            "unmodified OEM exterior body kit",
        ),
        modified_prompts=(
            "aftermarket body kit on a vehicle",
            "modified custom bumper spoiler side skirt",
            "non factory exterior body modification",
        ),
    ),
    PartPromptConfig(
        part="paint_or_wrap",
        views=("front", "front-left", "left", "rear-left", "rear", "rear-right", "right", "front-right"),
        stock_prompts=(
            "factory stock vehicle paint",
            "standard original manufacturer paint color",
            "normal single color car paint finish",
        ),
        modified_prompts=(
            "custom vehicle wrap or vinyl graphics",
            "aftermarket custom paint job",
            "non factory decal wrap livery",
        ),
    ),
    PartPromptConfig(
        part="interior",
        views=("interior", "dashboard", "odometer"),
        stock_prompts=(
            "factory stock vehicle interior",
            "original manufacturer dashboard and steering wheel",
            "standard OEM car cabin",
        ),
        modified_prompts=(
            "aftermarket modified vehicle interior",
            "custom steering wheel gauges or electronics",
            "non factory interior modification",
        ),
    ),
)


class ModificationDetector:
    """Detect visible stock-vs-modified part categories from organized frames."""

    def __init__(self, clip_model=None, clip_processor=None):
        self.clip_model = clip_model
        self.clip_processor = clip_processor
        self._text_embedding_cache: Dict[str, Any] = {}

    async def detect(
        self,
        frame_paths: List[str],
        frame_analysis: Optional[Dict[str, Any]] = None,
        exhaust: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(self._detect_sync, frame_paths, frame_analysis or {}, exhaust or {})

    def _detect_sync(
        self,
        frame_paths: List[str],
        frame_analysis: Dict[str, Any],
        exhaust: Dict[str, Any],
    ) -> Dict[str, Any]:
        items: List[Dict[str, Any]] = []
        exhaust_item = self._exhaust_item(exhaust)
        if exhaust_item:
            items.append(exhaust_item)

        if not self._clip_available():
            return {
                "available": False,
                "reason": "CLIP model unavailable for local modification detection",
                "items": items,
                "summary": self._summary(items, clip_available=False),
            }

        for config in PART_PROMPTS:
            part_items = self._classify_part(config, frame_paths, frame_analysis)
            if part_items:
                items.append(part_items)

        return {
            "available": True,
            "method": "clip_zero_shot_part_prompts",
            "items": items,
            "summary": self._summary(items, clip_available=True),
        }

    def _classify_part(
        self,
        config: PartPromptConfig,
        frame_paths: List[str],
        frame_analysis: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        images_with_meta = self._images_for_part(config, frame_paths, frame_analysis)
        if not images_with_meta:
            return {
                "part": config.part,
                "status": "unknown",
                "confidence": 0.0,
                "source": "local_clip",
                "notes": "No usable organized frames for this part category.",
            }

        prompts = list(config.stock_prompts) + list(config.modified_prompts)
        stock_count = len(config.stock_prompts)
        try:
            text_features = self._text_embeddings(config.part, prompts)
            images = [item["image"] for item in images_with_meta]

            import torch

            with torch.no_grad():
                image_inputs = self.clip_processor(images=images, return_tensors="pt")
                image_features = clip_features_to_tensor(self.clip_model.get_image_features(**image_inputs))
                image_features = image_features / image_features.norm(dim=-1, keepdim=True)
                logits = (image_features @ text_features.T) * 100.0
                grouped = torch.stack(
                    [
                        logits[:, :stock_count].max(dim=1).values,
                        logits[:, stock_count:].max(dim=1).values,
                    ],
                    dim=1,
                )
                probs = torch.softmax(grouped, dim=1)
                best_confidence, best_status_idx = probs.max(dim=1)
                best_frame_idx = int(best_confidence.argmax().item())
                stock_prob = float(probs[best_frame_idx, 0].item())
                modified_prob = float(probs[best_frame_idx, 1].item())
        except Exception as exc:
            logger.warning("ModificationDetector: CLIP failed for %s: %s", config.part, exc, exc_info=True)
            return {
                "part": config.part,
                "status": "unknown",
                "confidence": 0.0,
                "source": "local_clip",
                "notes": f"CLIP scoring failed for this part category: {exc}",
            }

        status = "stock" if int(best_status_idx[best_frame_idx].item()) == 0 else "modified"
        confidence = stock_prob if status == "stock" else modified_prob
        margin = abs(stock_prob - modified_prob)
        meta = images_with_meta[best_frame_idx]["meta"]

        threshold = (
            _MODIFIED_CONFIDENCE_THRESHOLD
            if status == "modified"
            else _STOCK_CONFIDENCE_THRESHOLD
        )
        margin_threshold = (
            _MODIFIED_MARGIN_THRESHOLD
            if status == "modified"
            else _STOCK_MARGIN_THRESHOLD
        )

        if confidence < threshold or margin < margin_threshold:
            return {
                "part": config.part,
                "status": "unknown",
                "confidence": round(confidence, 4),
                "source": "local_clip",
                "frame": meta.get("frame"),
                "view": meta.get("view"),
                "frame_index": meta.get("frame_index"),
                "source_frame_index": meta.get("source_frame_index"),
                "timestamp_seconds": meta.get("timestamp_seconds"),
                "notes": (
                    f"Local CLIP score was ambiguous "
                    f"(stock={stock_prob:.3f}, modified={modified_prob:.3f}, "
                    f"required_confidence={threshold:.3f}, required_margin={margin_threshold:.3f})."
                ),
            }

        return {
            "part": config.part,
            "status": status,
            "confidence": round(confidence, 4),
            "source": "local_clip",
            "frame": meta.get("frame"),
            "view": meta.get("view"),
            "frame_index": meta.get("frame_index"),
            "source_frame_index": meta.get("source_frame_index"),
            "timestamp_seconds": meta.get("timestamp_seconds"),
            "notes": (
                f"Local CLIP prompt comparison favored {status} "
                f"(stock={stock_prob:.3f}, modified={modified_prob:.3f})."
            ),
        }

    def _text_embeddings(self, cache_key: str, prompts: List[str]):
        if cache_key in self._text_embedding_cache:
            return self._text_embedding_cache[cache_key]

        import torch

        with torch.no_grad():
            inputs = self.clip_processor(text=prompts, return_tensors="pt", padding=True, truncation=True)
            text_features = clip_features_to_tensor(self.clip_model.get_text_features(**inputs))
            text_features = text_features / text_features.norm(dim=-1, keepdim=True)
        self._text_embedding_cache[cache_key] = text_features
        return text_features

    def _images_for_part(
        self,
        config: PartPromptConfig,
        frame_paths: List[str],
        frame_analysis: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        candidates: List[Dict[str, Any]] = []
        by_view = self._organized_frames_by_view(frame_analysis)
        for view in config.views:
            payload = by_view.get(view)
            if payload:
                candidates.append(payload)

        if not candidates:
            candidates = [
                {"view": "frame", "frame": path}
                for path in frame_paths[:_MAX_IMAGES_PER_PART]
            ]

        images: List[Dict[str, Any]] = []
        seen_paths: set[str] = set()
        for payload in candidates:
            path = payload.get("organized_path") or payload.get("frame")
            if not path or path in seen_paths or not os.path.exists(path):
                continue
            try:
                images.append({"image": Image.open(path).convert("RGB"), "meta": payload})
                seen_paths.add(path)
            except Exception:
                continue
            if len(images) >= _MAX_IMAGES_PER_PART:
                break
        return images

    @staticmethod
    def _organized_frames_by_view(frame_analysis: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {}
        angle_shots = frame_analysis.get("angle_shots") if isinstance(frame_analysis.get("angle_shots"), dict) else {}
        for view, payload in angle_shots.items():
            if isinstance(payload, dict):
                item = dict(payload)
                item.setdefault("view", view)
                out[view] = item
        for payload in frame_analysis.get("representative_frames") or []:
            if isinstance(payload, dict) and payload.get("view") and payload.get("view") not in out:
                out[str(payload["view"])] = dict(payload)
        return out

    @staticmethod
    def _exhaust_item(exhaust: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        exhaust_type = str(exhaust.get("type") or "").strip().lower()
        if exhaust_type not in {"stock", "modified"}:
            return None
        return {
            "part": "exhaust",
            "status": exhaust_type,
            "confidence": exhaust.get("confidence"),
            "source": "exhaust_classifier",
            "frame": exhaust.get("exhaust_image_path"),
            "notes": "Derived from exhaust classifier.",
        }

    @staticmethod
    def _summary(items: List[Dict[str, Any]], *, clip_available: bool) -> str:
        concrete = [
            f"{item.get('part')}: {item.get('status')}"
            for item in items
            if item.get("status") in {"stock", "modified"}
        ]
        if concrete:
            prefix = "Local CLIP modification scan" if clip_available else "Local modification scan"
            return f"{prefix} produced concrete evidence for {', '.join(concrete)}."
        if clip_available:
            return "Local CLIP modification scan found no concrete stock-vs-modified evidence."
        return "Only exhaust classifier evidence is available; CLIP/VLM is required for other visible parts."

    def _clip_available(self) -> bool:
        return self.clip_model is not None and self.clip_processor is not None
