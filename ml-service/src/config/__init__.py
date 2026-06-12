"""Configuration module for ML service."""

from .constants import (
    MODELS,
    FRAME_EXTRACTION,
)
from .env import load_ml_environment

__all__ = [
    "MODELS",
    "FRAME_EXTRACTION",
    "load_ml_environment",
]
