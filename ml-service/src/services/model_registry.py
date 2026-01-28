"""
Model Registry for singleton ML model management
Provides centralized loading and access to ML models to avoid redundant loading per request
"""

import os
import time
import logging
from typing import Optional
from ultralytics import YOLO

logger = logging.getLogger(__name__)


class ModelRegistry:
    """
    Singleton registry for ML models.
    Loads models once at application startup and provides access to shared instances.
    """

    def __init__(self):
        self._yolo_model: Optional[YOLO] = None
        self._clip_model = None
        self._clip_processor = None
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
                resume_download=True
            )
            logger.info(f"CLIP model loaded in {time.time() - start_time:.2f}s")

            logger.info("Loading CLIP processor...")
            processor_start = time.time()
            self._clip_processor = CLIPProcessor.from_pretrained(
                model_name,
                local_files_only=False,
                resume_download=True
            )
            logger.info(f"CLIP processor loaded in {time.time() - processor_start:.2f}s")
            logger.info(f"Total CLIP initialization: {time.time() - start_time:.2f}s")

        except Exception as e:
            logger.error(f"Failed to load CLIP model: {e}", exc_info=True)
            logger.error("Possible causes: network issues, HuggingFace Hub unavailable, disk space, permissions")
            raise RuntimeError(f"Failed to load CLIP model: {e}") from e

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


# Global singleton instance
_registry: Optional[ModelRegistry] = None


def get_model_registry() -> ModelRegistry:
    """Get the global ModelRegistry singleton instance."""
    global _registry
    if _registry is None:
        _registry = ModelRegistry()
    return _registry
