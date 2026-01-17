"""
Dashboard detection service
Detects dashboard region in vehicle frames using YOLOv8
"""

import asyncio
from typing import List
from ultralytics import YOLO
from PIL import Image
import cv2
import numpy as np


class DashboardDetector:
    """Detects dashboard/speedometer region in vehicle frames"""

    def __init__(self):
        """Initialize dashboard detector"""
        # Load YOLOv8 model
        # Note: For MVP, we'll use a general object detector
        # In production, you'd use a custom-trained model for dashboards
        print("Loading YOLOv8 model for dashboard detection...")
        self.yolo_model = YOLO("yolov8n.pt")

    async def detect(self, frame_paths: List[str]) -> List[str]:
        """
        Detect dashboard regions in frames
        Args:
            frame_paths: List of frame image paths
        Returns:
            List of dashboard image paths (cropped regions)
        """
        return await asyncio.to_thread(self._detect_sync, frame_paths)

    def _detect_sync(self, frame_paths: List[str]) -> List[str]:
        """
        Synchronous dashboard detection
        """
        dashboard_frames = []

        for frame_path in frame_paths[:10]:  # Check first 10 frames
            try:
                # Load image
                image = cv2.imread(frame_path)
                if image is None:
                    continue

                # Use YOLO to detect objects
                # Look for objects that might be dashboard components
                results = self.yolo_model(frame_path)

                # For MVP, we'll extract the center-upper region
                # which typically contains the dashboard
                height, width = image.shape[:2]
                
                # Extract upper-middle region (typical dashboard location)
                x1 = int(width * 0.1)
                y1 = int(height * 0.1)
                x2 = int(width * 0.9)
                y2 = int(height * 0.4)
                
                dashboard_region = image[y1:y2, x1:x2]

                # Save dashboard region
                dashboard_path = frame_path.replace(".jpg", "_dashboard.jpg")
                cv2.imwrite(dashboard_path, dashboard_region)
                dashboard_frames.append(dashboard_path)

            except Exception as e:
                print(f"Dashboard detection error for {frame_path}: {e}")
                continue

        return dashboard_frames
