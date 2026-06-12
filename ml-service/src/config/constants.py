"""
Centralized constants for ML service.
Single source of truth for model names and frame-extraction defaults.

No model name is hardcoded at call sites: everything resolves through MODELS,
which reads environment overrides so weights can be swapped (or a fine-tuned
CarDD model dropped in) without code changes.
"""

import os

# Model Configuration (env-overridable; defaults preserve previous behavior).
#   ML_YOLO_MODEL          — general object-detection weights (vehicle region,
#                            dashboard, exhaust grounding). COCO classes assumed.
#   ML_CLIP_MODEL          — CLIP weights for frame selection / vehicle ID only.
#                            CLIP is never used for damage detection.
#   ML_DAMAGE_MODEL_PATH   — dedicated damage detection/segmentation weights
#                            (e.g. a CarDD-trained YOLO or RT-DETR export).
#                            Empty disables the local detector (VLM-only mode).
#   ML_DAMAGE_MODEL_ARCH   — "auto" | "yolo" | "rtdetr". "auto" picks RT-DETR
#                            when the filename contains "rtdetr".
MODELS = {
    "yolo": os.getenv("ML_YOLO_MODEL", "").strip() or "yolov8n.pt",
    "clip": os.getenv("ML_CLIP_MODEL", "").strip() or "openai/clip-vit-base-patch32",
    "damage": os.getenv("ML_DAMAGE_MODEL_PATH", "").strip(),
    "damage_arch": (os.getenv("ML_DAMAGE_MODEL_ARCH", "").strip() or "auto").lower(),
}

# Detection Thresholds
FRAME_EXTRACTION = {
    "fps": 2,
    "min_blur_threshold": 15.0,
    "jpeg_quality": 98,
}
