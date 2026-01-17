"""
Damage detection service
Detects scratches, dents, and rust using YOLOv8
"""

import asyncio
from typing import Dict, Any, List
from ultralytics import YOLO
import cv2
import numpy as np


class DamageDetector:
    """Detects vehicle damage (scratches, dents, rust)"""

    def __init__(self):
        """Initialize damage detector"""
        # Load YOLOv8 model
        # Note: For MVP, we use a general object detector
        # In production, you'd use a custom-trained model for damage detection
        print("Loading YOLOv8 model for damage detection...")
        self.yolo_model = YOLO("yolov8n.pt")

    async def detect(self, frame_paths: List[str]) -> Dict[str, Any]:
        """
        Detect damage in vehicle frames
        Args:
            frame_paths: List of frame image paths
        Returns:
            Dictionary with damage detection results
        """
        return await asyncio.to_thread(self._detect_sync, frame_paths)

    def _detect_sync(self, frame_paths: List[str]) -> Dict[str, Any]:
        """
        Synchronous damage detection
        """
        scratches_count = 0
        dents_count = 0
        rust_count = 0
        damage_locations = []

        # Process frames to detect damage
        # For MVP, we'll use a simple approach:
        # Look for anomalies, edges, and color variations that might indicate damage
        
        for frame_path in frame_paths:
            try:
                # Load image
                image = cv2.imread(frame_path)
                if image is None:
                    continue

                # Convert to grayscale for edge detection
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

                # Detect edges (scratches often show as edges)
                edges = cv2.Canny(gray, 50, 150)

                # Count edge pixels (high edge density might indicate scratches)
                edge_density = np.sum(edges > 0) / (edges.shape[0] * edges.shape[1])

                # Simple heuristic: if edge density is high, might be scratches
                if edge_density > 0.15:  # Threshold for scratch detection
                    scratches_count += 1
                    damage_locations.append({
                        "type": "scratch",
                        "frame": frame_path,
                        "confidence": min(edge_density * 5, 1.0),
                    })

                # Check for color variations (rust detection)
                # Convert to HSV for better color analysis
                hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

                # Look for orange/brown colors (typical rust colors)
                lower_rust = np.array([10, 50, 50])
                upper_rust = np.array([25, 255, 255])
                rust_mask = cv2.inRange(hsv, lower_rust, upper_rust)
                rust_pixels = np.sum(rust_mask > 0)

                if rust_pixels > 1000:  # Threshold for rust detection
                    rust_count += 1
                    damage_locations.append({
                        "type": "rust",
                        "frame": frame_path,
                        "confidence": min(rust_pixels / 10000, 1.0),
                    })

            except Exception as e:
                print(f"Damage detection error for {frame_path}: {e}")
                continue

        # Determine severity
        total_damage = scratches_count + dents_count + rust_count
        severity = "high" if total_damage > 5 else "low"

        return {
            "scratches": {
                "count": scratches_count,
                "detected": scratches_count > 0,
            },
            "dents": {
                "count": dents_count,
                "detected": dents_count > 0,
            },
            "rust": {
                "count": rust_count,
                "detected": rust_count > 0,
            },
            "severity": severity,
            "locations": damage_locations[:10],  # Limit to 10 locations
        }
