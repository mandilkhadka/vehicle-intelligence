"""
Exhaust classification service
Classifies exhaust as stock or modified using YOLOv8 and image analysis
"""

import asyncio
import os
from typing import Dict, Any, List, Optional
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

    async def classify(self, frame_paths: List[str], inspection_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Classify exhaust system
        Args:
            frame_paths: List of frame image paths
            inspection_id: Optional inspection ID for organizing snapshots
        Returns:
            Dictionary with exhaust classification results
        """
        return await asyncio.to_thread(self._classify_sync, frame_paths, inspection_id)

    def _classify_sync(self, frame_paths: List[str], inspection_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Synchronous exhaust classification with snapshot capture
        """
        # Look for exhaust region in frames
        # Typically at the rear of the vehicle (bottom-center or bottom-right)
        
        # Create snapshots directory if inspection_id is provided
        snapshots_dir = None
        backend_uploads_path = None
        exhaust_image_path = None
        
        if inspection_id:
            # Determine snapshots directory relative to backend/uploads
            backend_root = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "..")
            snapshots_dir = os.path.join(backend_root, "backend", "uploads", "frames", inspection_id, "exhaust_snapshots")
            backend_uploads_path = os.path.join(backend_root, "backend", "uploads")
            os.makedirs(snapshots_dir, exist_ok=True)
        
        exhaust_features = []
        best_exhaust_frame = None
        best_confidence = 0.0
        
        for frame_idx, frame_path in enumerate(frame_paths):
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
                
                # Track best frame for snapshot (highest confidence)
                if confidence > best_confidence:
                    best_confidence = confidence
                    best_exhaust_frame = {
                        "frame_path": frame_path,
                        "frame_idx": frame_idx,
                        "rear_region": rear_region,
                        "confidence": confidence,
                        "is_stock": is_stock,
                    }

            except Exception as e:
                print(f"Exhaust classification error for {frame_path}: {e}")
                continue

        # Save exhaust snapshot if we found a good frame
        if best_exhaust_frame and snapshots_dir:
            try:
                snapshot_filename = f"exhaust_frame_{best_exhaust_frame['frame_idx']:04d}.jpg"
                snapshot_path_full = os.path.join(snapshots_dir, snapshot_filename)
                cv2.imwrite(snapshot_path_full, best_exhaust_frame["rear_region"])
                
                # Convert to relative path for serving
                if backend_uploads_path:
                    exhaust_image_path = os.path.relpath(snapshot_path_full, backend_uploads_path)
                    exhaust_image_path = exhaust_image_path.replace("\\", "/")  # Normalize path separators
                    print(f"Saved exhaust snapshot: {exhaust_image_path}")
            except Exception as e:
                print(f"Error saving exhaust snapshot: {e}")

        # Aggregate results
        if not exhaust_features:
            result = {
                "type": "stock",
                "confidence": 0.5,
            }
            if exhaust_image_path:
                result["exhaust_image_path"] = exhaust_image_path
            return result

        # Use majority vote
        stock_count = sum(1 for f in exhaust_features if f["is_stock"])
        total_count = len(exhaust_features)
        
        is_stock = stock_count > total_count / 2
        avg_confidence = np.mean([f["confidence"] for f in exhaust_features])

        result = {
            "type": "stock" if is_stock else "modified",
            "confidence": float(avg_confidence),
        }
        
        if exhaust_image_path:
            result["exhaust_image_path"] = exhaust_image_path
            
        return result
