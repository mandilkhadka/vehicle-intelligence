"""
Exhaust classification service
Classifies exhaust as stock or modified using YOLOv8 and image analysis
"""

import asyncio
from typing import Dict, Any, List
from ultralytics import YOLO
import cv2
import numpy as np


class ExhaustClassifier:
    """Classifies exhaust system as stock or modified"""

    def __init__(self):
        """Initialize exhaust classifier"""
        # Load YOLOv8 model for object detection
        print("Loading YOLOv8 model for exhaust detection...")
        self.yolo_model = YOLO("yolov8n.pt")

    async def classify(self, frame_paths: List[str]) -> Dict[str, Any]:
        """
        Classify exhaust system
        Args:
            frame_paths: List of frame image paths
        Returns:
            Dictionary with exhaust classification results
        """
        return await asyncio.to_thread(self._classify_sync, frame_paths)

    def _classify_sync(self, frame_paths: List[str]) -> Dict[str, Any]:
        """
        Synchronous exhaust classification
        """
        # Look for exhaust region in frames
        # Typically at the rear of the vehicle (bottom-center or bottom-right)
        
        exhaust_features = []
        
        for frame_path in frame_paths:
            try:
                # Load image
                image = cv2.imread(frame_path)
                if image is None:
                    continue

                height, width = image.shape[:2]

                # Extract rear region (where exhaust typically is)
                # Bottom portion of the image
                rear_region = image[int(height * 0.7) :, :]

                if rear_region.size == 0:
                    continue

                # Analyze exhaust region
                # Modified exhausts often have:
                # - Different shapes (larger, more angular)
                # - Different colors (chrome, black, aftermarket materials)
                # - More complex structures

                # Convert to grayscale
                gray = cv2.cvtColor(rear_region, cv2.COLOR_BGR2GRAY)

                # Detect edges
                edges = cv2.Canny(gray, 50, 150)
                edge_complexity = np.sum(edges > 0) / (edges.shape[0] * edges.shape[1])

                # Check for circular shapes (typical stock exhaust)
                circles = cv2.HoughCircles(
                    gray,
                    cv2.HOUGH_GRADIENT,
                    1,
                    20,
                    param1=50,
                    param2=30,
                    minRadius=10,
                    maxRadius=50,
                )

                # Simple heuristic:
                # Stock exhausts are usually simpler (circular, uniform)
                # Modified exhausts are more complex (angular, varied shapes)
                is_stock = False
                confidence = 0.5

                if circles is not None and len(circles[0]) > 0:
                    # Found circular shapes - likely stock
                    is_stock = True
                    confidence = 0.7
                elif edge_complexity > 0.2:
                    # High edge complexity - might be modified
                    is_stock = False
                    confidence = 0.6
                else:
                    # Default to stock
                    is_stock = True
                    confidence = 0.5

                exhaust_features.append({
                    "is_stock": is_stock,
                    "confidence": confidence,
                    "frame": frame_path,
                })

            except Exception as e:
                print(f"Exhaust classification error for {frame_path}: {e}")
                continue

        # Aggregate results
        if not exhaust_features:
            return {
                "type": "stock",
                "confidence": 0.5,
            }

        # Use majority vote
        stock_count = sum(1 for f in exhaust_features if f["is_stock"])
        total_count = len(exhaust_features)
        
        is_stock = stock_count > total_count / 2
        avg_confidence = np.mean([f["confidence"] for f in exhaust_features])

        return {
            "type": "stock" if is_stock else "modified",
            "confidence": float(avg_confidence),
        }
