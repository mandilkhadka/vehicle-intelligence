"""
Model Registry for singleton ML model management
Provides centralized loading and access to ML models to avoid redundant loading per request
"""

import os
import time
import logging
from typing import Optional, List
from ultralytics import YOLO

logger = logging.getLogger(__name__)


# Brand catalog used for CLIP zero-shot identification.
# Kept in the registry so the precomputed text embeddings stay aligned with this list.
VEHICLE_BRANDS: List[str] = [
    "Toyota", "Honda", "Ford", "Chevrolet", "Nissan",
    "BMW", "Mercedes-Benz", "Audi", "Volkswagen", "Hyundai",
    "Kia", "Mazda", "Subaru", "Jeep", "Lexus",
    "Tesla", "Porsche", "Jaguar", "Land Rover", "Volvo",
]

# Prompt ensemble — averaging text embeddings across several templates is a
# well-known zero-shot CLIP accuracy trick (see CLIP paper §3.1.4).
BRAND_PROMPT_TEMPLATES: List[str] = [
    "a photo of a {brand} car",
    "a {brand} automobile",
    "a high-quality photo of a {brand} vehicle",
    "the front of a {brand} car",
    "a {brand} logo on a car",
    "a clear picture of a {brand} vehicle",
]


def clip_features_to_tensor(features):
    """Return the projected CLIP embedding tensor across Transformers versions."""
    if hasattr(features, "pooler_output"):
        return features.pooler_output
    if isinstance(features, (tuple, list)):
        return features[0]
    return features


class ModelRegistry:
    """
    Singleton registry for ML models.
    Loads models once at application startup and provides access to shared instances.
    """

    def __init__(self):
        self._yolo_model: Optional[YOLO] = None
        self._clip_model = None
        self._clip_processor = None
        # Precomputed L2-normalized brand text embeddings (shape: [num_brands, embed_dim])
        self._brand_text_embeddings = None
        self._brand_names: List[str] = list(VEHICLE_BRANDS)
        self._initialized = False

    @property
    def is_initialized(self) -> bool:
        """Check if all models have been initialized."""
        return self._initialized

    def initialize_all_models(self) -> None:
        """
        Initialize all ML models.
        Should be called once at application startup.
        """
        if self._initialized:
            logger.warning("ModelRegistry already initialized, skipping re-initialization")
            return

        total_start = time.time()
        logger.info("=" * 60)
        logger.info("MODEL REGISTRY: Starting model initialization...")
        logger.info("=" * 60)

        # Load YOLOv8 model (shared across all detectors)
        self._load_yolo_model()

        # Load CLIP model and processor (for vehicle identification)
        self._load_clip_models()

        # Precompute brand text embeddings (depends on CLIP being loaded)
        self._precompute_brand_text_embeddings()

        self._initialized = True
        total_time = time.time() - total_start
        logger.info("=" * 60)
        logger.info(f"MODEL REGISTRY: All models initialized in {total_time:.2f}s")
        logger.info("=" * 60)

    def _load_yolo_model(self) -> None:
        """Load YOLOv8 nano model for object detection."""
        logger.info("Loading YOLOv8 model...")
        start_time = time.time()
        try:
            self._yolo_model = YOLO("yolov8n.pt")
            logger.info(f"YOLOv8 model loaded in {time.time() - start_time:.2f}s")
        except Exception as e:
            logger.error(f"Failed to load YOLOv8 model: {e}", exc_info=True)
            raise RuntimeError(f"Failed to load YOLOv8 model: {e}") from e

    def _load_clip_models(self) -> None:
        """Load CLIP model and processor for vehicle identification."""
        from transformers import CLIPProcessor, CLIPModel

        model_name = "openai/clip-vit-base-patch32"

        # Set environment variable to avoid hanging on network issues
        os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

        logger.info(f"Loading CLIP model ({model_name})...")
        logger.info("Note: First run may take 30-60 seconds to download model weights")
        start_time = time.time()

        try:
            self._clip_model = CLIPModel.from_pretrained(
                model_name,
                local_files_only=False,
            )
            logger.info(f"CLIP model loaded in {time.time() - start_time:.2f}s")

            logger.info("Loading CLIP processor...")
            processor_start = time.time()
            self._clip_processor = CLIPProcessor.from_pretrained(
                model_name,
                local_files_only=False,
            )
            logger.info(f"CLIP processor loaded in {time.time() - processor_start:.2f}s")
            logger.info(f"Total CLIP initialization: {time.time() - start_time:.2f}s")

        except Exception as e:
            logger.error(f"Failed to load CLIP model: {e}", exc_info=True)
            logger.error("Possible causes: network issues, HuggingFace Hub unavailable, disk space, permissions")
            raise RuntimeError(f"Failed to load CLIP model: {e}") from e

    def _precompute_brand_text_embeddings(self) -> None:
        """
        Build a [num_brands, embed_dim] tensor of L2-normalized text embeddings,
        averaged across a prompt ensemble. Done once at startup so per-request
        identification is just an image-encode + matmul.
        """
        import torch

        if self._clip_model is None or self._clip_processor is None:
            raise RuntimeError("Cannot precompute embeddings before CLIP is loaded")

        logger.info(
            f"Precomputing brand text embeddings: "
            f"{len(self._brand_names)} brands × {len(BRAND_PROMPT_TEMPLATES)} templates"
        )
        start_time = time.time()

        per_brand_embeddings = []
        with torch.no_grad():
            for brand in self._brand_names:
                prompts = [tpl.format(brand=brand) for tpl in BRAND_PROMPT_TEMPLATES]
                inputs = self._clip_processor(
                    text=prompts, return_tensors="pt", padding=True, truncation=True
                )
                text_features = clip_features_to_tensor(self._clip_model.get_text_features(**inputs))
                # L2-normalize each prompt embedding, then average across templates,
                # then L2-normalize again — this is the standard prompt-ensemble recipe.
                text_features = text_features / text_features.norm(dim=-1, keepdim=True)
                brand_embedding = text_features.mean(dim=0)
                brand_embedding = brand_embedding / brand_embedding.norm()
                per_brand_embeddings.append(brand_embedding)

        self._brand_text_embeddings = torch.stack(per_brand_embeddings, dim=0)
        logger.info(
            f"Brand text embeddings ready: shape={tuple(self._brand_text_embeddings.shape)} "
            f"in {time.time() - start_time:.2f}s"
        )

    def get_yolo_model(self) -> YOLO:
        """Get the shared YOLOv8 model instance."""
        if self._yolo_model is None:
            raise RuntimeError("YOLOv8 model not initialized. Call initialize_all_models() first.")
        return self._yolo_model

    def get_clip_model(self):
        """Get the shared CLIP model instance."""
        if self._clip_model is None:
            raise RuntimeError("CLIP model not initialized. Call initialize_all_models() first.")
        return self._clip_model

    def get_clip_processor(self):
        """Get the shared CLIP processor instance."""
        if self._clip_processor is None:
            raise RuntimeError("CLIP processor not initialized. Call initialize_all_models() first.")
        return self._clip_processor

    def get_brand_text_embeddings(self):
        """
        Get precomputed brand text embeddings (torch.Tensor [num_brands, embed_dim]).
        Returns None if not initialized — callers should fall back to on-the-fly encoding.
        """
        return self._brand_text_embeddings

    def get_brand_names(self) -> List[str]:
        """Get the brand list aligned with the precomputed text embeddings."""
        return list(self._brand_names)


# Global singleton instance
_registry: Optional[ModelRegistry] = None


def get_model_registry() -> ModelRegistry:
    """Get the global ModelRegistry singleton instance."""
    global _registry
    if _registry is None:
        _registry = ModelRegistry()
    return _registry
