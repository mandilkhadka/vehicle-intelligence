"""Configuration module for ML service."""

from .constants import (
    MODELS,
    FRAME_EXTRACTION,
    DAMAGE_DETECTION,
    COLOR_RANGES,
    VEHICLE_TYPES,
)
from .env import load_ml_environment

__all__ = [
    "MODELS",
    "FRAME_EXTRACTION",
    "DAMAGE_DETECTION",
    "COLOR_RANGES",
    "VEHICLE_TYPES",
    "load_ml_environment",
]
