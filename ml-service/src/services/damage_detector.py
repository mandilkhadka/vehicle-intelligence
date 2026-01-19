"""
Damage detection service
Detects scratches, dents, and rust using YOLOv8
"""

import asyncio
from typing import Dict, Any, List
from ultralytics import YOLO
import cv2
import numpy as np
import os
from pathlib import Path


class DamageDetector:
    """Detects vehicle damage (scratches, dents, rust)"""

    def __init__(self):
        """Initialize damage detector"""
        # Load YOLOv8 model
        # Note: For MVP, we use a general object detector
        # In production, you'd use a custom-trained model for damage detection
        print("Loading YOLOv8 model for damage detection...")
        self.yolo_model = YOLO("yolov8n.pt")

    async def detect(self, frame_paths: List[str], inspection_id: str = None) -> Dict[str, Any]:
        """
        Detect damage in vehicle frames
        Args:
            frame_paths: List of frame image paths
            inspection_id: Optional inspection ID for organizing snapshots
        Returns:
            Dictionary with damage detection results
        """
        return await asyncio.to_thread(self._detect_sync, frame_paths, inspection_id)

    def _detect_sync(self, frame_paths: List[str], inspection_id: str = None) -> Dict[str, Any]:
        """
        Synchronous damage detection with snapshot capture
        """
        scratches_count = 0
        dents_count = 0
        rust_count = 0
        damage_locations = []

        # Create snapshots directory if inspection_id is provided
        snapshots_dir = None
        backend_uploads_path = None
        if inspection_id:
            # Determine snapshots directory relative to backend/uploads
            backend_root = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "..")
            snapshots_dir = os.path.join(backend_root, "backend", "uploads", "frames", inspection_id, "damage_snapshots")
            backend_uploads_path = os.path.join(backend_root, "backend", "uploads")
            os.makedirs(snapshots_dir, exist_ok=True)

        # Process frames to detect damage
        # For MVP, we'll use a simple approach:
        # Look for anomalies, edges, and color variations that might indicate damage
        
        snapshot_counter = {"scratch": 0, "dent": 0, "rust": 0}
        
        for frame_idx, frame_path in enumerate(frame_paths):
            try:
                # Load image
                image = cv2.imread(frame_path)
                if image is None:
                    continue

                h, w = image.shape[:2]

                # Detect vehicle region first to focus on vehicle area
                vehicle_region = self._get_vehicle_region(image, frame_path)
                if vehicle_region is None:
                    vehicle_region = (0, 0, w, h)  # Use full image if vehicle not detected
                
                vx1, vy1, vx2, vy2 = vehicle_region
                vehicle_image = image[vy1:vy2, vx1:vx2]

                # Convert to grayscale for edge detection
                gray = cv2.cvtColor(vehicle_image, cv2.COLOR_BGR2GRAY)

                # Detect edges (scratches often show as edges)
                edges = cv2.Canny(gray, 50, 150)

                # Find contours of edge regions (potential scratches)
                contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                
                # Filter contours by size and detect scratches
                for contour in contours:
                    area = cv2.contourArea(contour)
                    if 100 < area < 50000:  # Reasonable size for scratches
                        x, y, w_contour, h_contour = cv2.boundingRect(contour)
                        
                        # Expand bounding box slightly for better context
                        padding = 20
                        x = max(0, x - padding)
                        y = max(0, y - padding)
                        w_contour = min(vehicle_image.shape[1] - x, w_contour + 2 * padding)
                        h_contour = min(vehicle_image.shape[0] - y, h_contour + 2 * padding)
                        
                        # Crop damage region
                        damage_crop = vehicle_image[y:y+h_contour, x:x+w_contour]
                        
                        if damage_crop.size > 0:
                            scratches_count += 1
                            snapshot_counter["scratch"] += 1
                            
                            # Save snapshot if directory is available
                            snapshot_path = None
                            if snapshots_dir:
                                snapshot_filename = f"scratch_{snapshot_counter['scratch']:03d}_frame_{frame_idx:04d}.jpg"
                                snapshot_path_full = os.path.join(snapshots_dir, snapshot_filename)
                                cv2.imwrite(snapshot_path_full, damage_crop)
                                
                                # Make path relative to backend/uploads
                                if backend_uploads_path:
                                    rel_path = os.path.relpath(snapshot_path_full, backend_uploads_path)
                                    snapshot_path = rel_path.replace("\\", "/")
                                else:
                                    snapshot_path = snapshot_path_full
                            
                            damage_locations.append({
                                "type": "scratch",
                                "frame": frame_path,
                                "snapshot": snapshot_path,
                                "confidence": min(area / 10000, 1.0),
                                "bbox": [vx1 + x, vy1 + y, vx1 + x + w_contour, vy1 + y + h_contour],
                            })

                # Check for color variations (rust detection)
                # Convert to HSV for better color analysis
                hsv = cv2.cvtColor(vehicle_image, cv2.COLOR_BGR2HSV)

                # Look for orange/brown colors (typical rust colors)
                lower_rust = np.array([10, 50, 50])
                upper_rust = np.array([25, 255, 255])
                rust_mask = cv2.inRange(hsv, lower_rust, upper_rust)
                
                # Find rust regions using contours
                rust_contours, _ = cv2.findContours(rust_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                
                for contour in rust_contours:
                    area = cv2.contourArea(contour)
                    if area > 1000:  # Threshold for rust detection
                        x, y, w_contour, h_contour = cv2.boundingRect(contour)
                        
                        # Expand bounding box
                        padding = 30
                        x = max(0, x - padding)
                        y = max(0, y - padding)
                        w_contour = min(vehicle_image.shape[1] - x, w_contour + 2 * padding)
                        h_contour = min(vehicle_image.shape[0] - y, h_contour + 2 * padding)
                        
                        # Crop rust region
                        rust_crop = vehicle_image[y:y+h_contour, x:x+w_contour]
                        
                        if rust_crop.size > 0:
                            rust_count += 1
                            snapshot_counter["rust"] += 1
                            
                            # Save snapshot
                            snapshot_path = None
                            if snapshots_dir:
                                snapshot_filename = f"rust_{snapshot_counter['rust']:03d}_frame_{frame_idx:04d}.jpg"
                                snapshot_path_full = os.path.join(snapshots_dir, snapshot_filename)
                                cv2.imwrite(snapshot_path_full, rust_crop)
                                
                                if backend_uploads_path:
                                    rel_path = os.path.relpath(snapshot_path_full, backend_uploads_path)
                                    snapshot_path = rel_path.replace("\\", "/")
                                else:
                                    snapshot_path = snapshot_path_full
                            
                            damage_locations.append({
                                "type": "rust",
                                "frame": frame_path,
                                "snapshot": snapshot_path,
                                "confidence": min(area / 10000, 1.0),
                                "bbox": [vx1 + x, vy1 + y, vx1 + x + w_contour, vy1 + y + h_contour],
                            })

                # Detect dents using depth/shadow analysis
                # Dents often create shadow patterns
                gray_blur = cv2.GaussianBlur(gray, (15, 15), 0)
                laplacian = cv2.Laplacian(gray_blur, cv2.CV_64F)
                laplacian_abs = np.abs(laplacian)
                
                # Threshold for dent-like patterns (circular depressions)
                _, dent_mask = cv2.threshold(laplacian_abs.astype(np.uint8), 30, 255, cv2.THRESH_BINARY)
                dent_contours, _ = cv2.findContours(dent_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                
                for contour in dent_contours:
                    area = cv2.contourArea(contour)
                    # Dents are typically larger than scratches
                    if 500 < area < 100000:
                        # Check circularity (dents are often circular)
                        perimeter = cv2.arcLength(contour, True)
                        if perimeter > 0:
                            circularity = 4 * np.pi * area / (perimeter * perimeter)
                            if circularity > 0.3:  # Somewhat circular
                                x, y, w_contour, h_contour = cv2.boundingRect(contour)
                                
                                # Expand bounding box
                                padding = 40
                                x = max(0, x - padding)
                                y = max(0, y - padding)
                                w_contour = min(vehicle_image.shape[1] - x, w_contour + 2 * padding)
                                h_contour = min(vehicle_image.shape[0] - y, h_contour + 2 * padding)
                                
                                # Crop dent region
                                dent_crop = vehicle_image[y:y+h_contour, x:x+w_contour]
                                
                                if dent_crop.size > 0:
                                    dents_count += 1
                                    snapshot_counter["dent"] += 1
                                    
                                    # Save snapshot
                                    snapshot_path = None
                                    if snapshots_dir:
                                        snapshot_filename = f"dent_{snapshot_counter['dent']:03d}_frame_{frame_idx:04d}.jpg"
                                        snapshot_path_full = os.path.join(snapshots_dir, snapshot_filename)
                                        cv2.imwrite(snapshot_path_full, dent_crop)
                                        
                                        if backend_uploads_path:
                                            rel_path = os.path.relpath(snapshot_path_full, backend_uploads_path)
                                            snapshot_path = rel_path.replace("\\", "/")
                                        else:
                                            snapshot_path = snapshot_path_full
                                    
                                    damage_locations.append({
                                        "type": "dent",
                                        "frame": frame_path,
                                        "snapshot": snapshot_path,
                                        "confidence": min(area / 50000, 1.0),
                                        "bbox": [vx1 + x, vy1 + y, vx1 + x + w_contour, vy1 + y + h_contour],
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
            "locations": damage_locations[:20],  # Limit to 20 locations
        }

    def _get_vehicle_region(self, image: np.ndarray, frame_path: str) -> tuple:
        """
        Get vehicle bounding box region from image
        Returns: (x1, y1, x2, y2) or None
        """
        try:
            results = self.yolo_model(frame_path)
            
            for result in results:
                boxes = result.boxes
                if boxes is not None:
                    for box in boxes:
                        class_id = int(box.cls[0])
                        # YOLO COCO classes: 2=car, 3=motorcycle, 7=truck
                        if class_id in [2, 3, 7]:
                            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                            return (int(x1), int(y1), int(x2), int(y2))
        except Exception as e:
            print(f"Vehicle region detection error: {e}")
        
        return None
