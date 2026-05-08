"""
Dashboard detection service
Crops the dashboard region out of vehicle frames so the OCR step has less area to scan.
"""

import asyncio
import logging
from typing import List, Optional
from ultralytics import YOLO
import cv2

logger = logging.getLogger(__name__)


class DashboardDetector:
    """Crops the upper-middle region of each frame as the dashboard candidate."""

    # YOLOv8 isn't trained on dashboard classes, so calling it here was a wasted
    # forward pass. The previous implementation ignored the YOLO output anyway
    # and fell back to a fixed crop. We accept yolo_model for backward-compat
    # with ModelRegistry callers but no longer run inference.
    def __init__(self, yolo_model: Optional[YOLO] = None):
        self.yolo_model = yolo_model

    async def detect(self, frame_paths: List[str]) -> List[str]:
        return await asyncio.to_thread(self._detect_sync, frame_paths)

    def _detect_sync(self, frame_paths: List[str]) -> List[str]:
        dashboard_frames: List[str] = []

        for frame_path in frame_paths[:10]:
            try:
                image = cv2.imread(frame_path)
                if image is None:
                    continue

                height, width = image.shape[:2]
                x1 = int(width * 0.1)
                y1 = int(height * 0.1)
                x2 = int(width * 0.9)
                y2 = int(height * 0.4)
                dashboard_region = image[y1:y2, x1:x2]

                dashboard_path = frame_path.replace(".jpg", "_dashboard.jpg")
                cv2.imwrite(dashboard_path, dashboard_region)
                dashboard_frames.append(dashboard_path)
            except Exception as e:
                logger.warning(f"Dashboard detection error for {frame_path}: {e}")
                continue

        return dashboard_frames
