"""
Damage detection service
Detects scratches, dents, and rust using YOLOv8 and computer vision
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
        Improved algorithm with better filtering and confidence calculation
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

        # Process frames to detect damage with improved filtering
        snapshot_counter = {"scratch": 0, "dent": 0, "rust": 0}
        
        # Track detected regions to avoid duplicates
        detected_regions = {"scratch": [], "dent": [], "rust": []}
        MIN_CONFIDENCE_THRESHOLD = 0.3  # Filter out detections below 30% confidence
        
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
                
                if vehicle_image.size == 0:
                    continue

                # Convert to grayscale for edge detection
                gray = cv2.cvtColor(vehicle_image, cv2.COLOR_BGR2GRAY)
                
                # Calculate image statistics for better filtering
                mean_intensity = np.mean(gray)
                std_intensity = np.std(gray)

                # Improved scratch detection with adaptive Canny edge detection
                sigma = 0.33
                median = np.median(gray)
                lower = int(max(0, (1.0 - sigma) * median))
                upper = int(min(255, (1.0 + sigma) * median))
                edges = cv2.Canny(gray, lower, upper)

                # Find contours of edge regions (potential scratches)
                contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                
                # Filter contours by size and detect scratches with improved confidence
                for contour in contours:
                    area = cv2.contourArea(contour)
                    # More restrictive size range for scratches
                    if 500 < area < 20000:  # Reasonable size for scratches
                        x, y, w_contour, h_contour = cv2.boundingRect(contour)
                        
                        # Check aspect ratio - scratches are usually elongated
                        aspect_ratio = max(w_contour, h_contour) / max(min(w_contour, h_contour), 1)
                        if aspect_ratio < 1.5:  # Skip if too square-like
                            continue
                        
                        # Check if region is significantly different from surroundings
                        padding = 30
                        x_pad = max(0, x - padding)
                        y_pad = max(0, y - padding)
                        w_pad = min(vehicle_image.shape[1] - x_pad, w_contour + 2 * padding)
                        h_pad = min(vehicle_image.shape[0] - y_pad, h_contour + 2 * padding)
                        
                        # Extract region and surrounding area
                        region = vehicle_image[y:y+h_contour, x:x+w_contour]
                        surrounding = vehicle_image[y_pad:y_pad+h_pad, x_pad:x_pad+w_pad]
                        
                        if region.size == 0:
                            continue
                        
                        # Calculate confidence based on edge strength and contrast
                        region_gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
                        surrounding_gray = cv2.cvtColor(surrounding, cv2.COLOR_BGR2GRAY)
                        
                        region_mean = np.mean(region_gray)
                        surrounding_mean = np.mean(surrounding_gray)
                        contrast = abs(region_mean - surrounding_mean) / 255.0
                        
                        # Edge density in the region
                        region_edges = cv2.Canny(region_gray, lower, upper)
                        edge_density = np.sum(region_edges > 0) / max(region_edges.size, 1)
                        
                        # Calculate confidence (0-1 scale)
                        # Higher contrast and edge density = higher confidence
                        confidence = min(0.95, 0.4 + (contrast * 0.4) + (edge_density * 0.2))
                        
                        # Filter low confidence detections
                        if confidence < MIN_CONFIDENCE_THRESHOLD:
                            continue
                        
                        # Check for duplicates (same location in nearby frames)
                        center_x = vx1 + x + w_contour // 2
                        center_y = vy1 + y + h_contour // 2
                        is_duplicate = False
                        for prev_region in detected_regions["scratch"]:
                            prev_x, prev_y, prev_frame = prev_region
                            # If same location within 50 pixels and within 3 frames, consider duplicate
                            if abs(prev_x - center_x) < 50 and abs(prev_y - center_y) < 50 and abs(prev_frame - frame_idx) < 3:
                                is_duplicate = True
                                break
                        
                        if is_duplicate:
                            continue
                        
                        # Expand bounding box slightly for better context
                        x_expanded = max(0, x - padding)
                        y_expanded = max(0, y - padding)
                        w_expanded = min(vehicle_image.shape[1] - x_expanded, w_contour + 2 * padding)
                        h_expanded = min(vehicle_image.shape[0] - y_expanded, h_contour + 2 * padding)
                        
                        # Crop damage region
                        damage_crop = vehicle_image[y_expanded:y_expanded+h_expanded, x_expanded:x_expanded+w_expanded]
                        
                        if damage_crop.size > 0:
                            scratches_count += 1
                            snapshot_counter["scratch"] += 1
                            detected_regions["scratch"].append((center_x, center_y, frame_idx))
                            
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
                                "confidence": confidence,
                                "bbox": [vx1 + x_expanded, vy1 + y_expanded, vx1 + x_expanded + w_expanded, vy1 + y_expanded + h_expanded],
                            })

                # Improved rust detection with better color filtering
                hsv = cv2.cvtColor(vehicle_image, cv2.COLOR_BGR2HSV)

                # Look for orange/brown colors (typical rust colors) - expanded range
                lower_rust1 = np.array([0, 50, 50])
                upper_rust1 = np.array([25, 255, 255])
                lower_rust2 = np.array([10, 30, 30])
                upper_rust2 = np.array([30, 255, 200])
                
                rust_mask1 = cv2.inRange(hsv, lower_rust1, upper_rust1)
                rust_mask2 = cv2.inRange(hsv, lower_rust2, upper_rust2)
                rust_mask = cv2.bitwise_or(rust_mask1, rust_mask2)
                
                # Apply morphological operations to reduce noise
                kernel = np.ones((5, 5), np.uint8)
                rust_mask = cv2.morphologyEx(rust_mask, cv2.MORPH_CLOSE, kernel)
                rust_mask = cv2.morphologyEx(rust_mask, cv2.MORPH_OPEN, kernel)
                
                # Find rust regions using contours
                rust_contours, _ = cv2.findContours(rust_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                
                for contour in rust_contours:
                    area = cv2.contourArea(contour)
                    if area > 2000:  # Higher threshold for rust detection
                        x, y, w_contour, h_contour = cv2.boundingRect(contour)
                        
                        # Calculate rust color saturation and intensity
                        rust_region_hsv = hsv[y:y+h_contour, x:x+w_contour]
                        rust_saturation = np.mean(rust_region_hsv[:, :, 1])
                        rust_value = np.mean(rust_region_hsv[:, :, 2])
                        
                        # Confidence based on color intensity and area
                        color_confidence = min(0.9, (rust_saturation / 255.0) * 0.5 + (rust_value / 255.0) * 0.3)
                        area_confidence = min(0.9, area / 50000.0)
                        confidence = (color_confidence + area_confidence) / 2.0
                        
                        if confidence < MIN_CONFIDENCE_THRESHOLD:
                            continue
                        
                        # Check for duplicates
                        center_x = vx1 + x + w_contour // 2
                        center_y = vy1 + y + h_contour // 2
                        is_duplicate = False
                        for prev_region in detected_regions["rust"]:
                            prev_x, prev_y, prev_frame = prev_region
                            if abs(prev_x - center_x) < 80 and abs(prev_y - center_y) < 80 and abs(prev_frame - frame_idx) < 3:
                                is_duplicate = True
                                break
                        
                        if is_duplicate:
                            continue
                        
                        # Expand bounding box
                        padding = 30
                        x_expanded = max(0, x - padding)
                        y_expanded = max(0, y - padding)
                        w_expanded = min(vehicle_image.shape[1] - x_expanded, w_contour + 2 * padding)
                        h_expanded = min(vehicle_image.shape[0] - y_expanded, h_contour + 2 * padding)
                        
                        # Crop rust region
                        rust_crop = vehicle_image[y_expanded:y_expanded+h_expanded, x_expanded:x_expanded+w_expanded]
                        
                        if rust_crop.size > 0:
                            rust_count += 1
                            snapshot_counter["rust"] += 1
                            detected_regions["rust"].append((center_x, center_y, frame_idx))
                            
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
                                "confidence": confidence,
                                "bbox": [vx1 + x_expanded, vy1 + y_expanded, vx1 + x_expanded + w_expanded, vy1 + y_expanded + h_expanded],
                            })

                # Improved dent detection using depth/shadow analysis
                gray_blur = cv2.GaussianBlur(gray, (15, 15), 0)
                laplacian = cv2.Laplacian(gray_blur, cv2.CV_64F)
                laplacian_abs = np.abs(laplacian)
                
                # Normalize laplacian
                laplacian_norm = ((laplacian_abs - laplacian_abs.min()) / (laplacian_abs.max() - laplacian_abs.min() + 1e-8) * 255).astype(np.uint8)
                
                # Threshold for dent-like patterns (circular depressions)
                _, dent_mask = cv2.threshold(laplacian_norm, 40, 255, cv2.THRESH_BINARY)
                
                # Apply morphological operations
                kernel = np.ones((7, 7), np.uint8)
                dent_mask = cv2.morphologyEx(dent_mask, cv2.MORPH_CLOSE, kernel)
                
                dent_contours, _ = cv2.findContours(dent_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                
                for contour in dent_contours:
                    area = cv2.contourArea(contour)
                    # Dents are typically larger than scratches
                    if 2000 < area < 100000:
                        # Check circularity (dents are often circular)
                        perimeter = cv2.arcLength(contour, True)
                        if perimeter > 0:
                            circularity = 4 * np.pi * area / (perimeter * perimeter)
                            if circularity > 0.4:  # More circular
                                x, y, w_contour, h_contour = cv2.boundingRect(contour)
                                
                                # Analyze shadow pattern (dents create shadows)
                                dent_region = gray[y:y+h_contour, x:x+w_contour]
                                if dent_region.size == 0:
                                    continue
                                
                                # Check for shadow gradient (darker in center)
                                center_y_idx, center_x_idx = h_contour // 2, w_contour // 2
                                center_intensity = dent_region[center_y_idx, center_x_idx]
                                edge_intensity = np.mean([
                                    dent_region[0, :].mean(),
                                    dent_region[-1, :].mean(),
                                    dent_region[:, 0].mean(),
                                    dent_region[:, -1].mean()
                                ])
                                
                                shadow_contrast = (edge_intensity - center_intensity) / 255.0
                                
                                # Calculate confidence
                                area_confidence = min(0.8, area / 50000.0)
                                circularity_confidence = min(0.7, circularity)
                                shadow_confidence = min(0.6, shadow_contrast * 2)
                                confidence = (area_confidence * 0.3 + circularity_confidence * 0.3 + shadow_confidence * 0.4)
                                
                                if confidence < MIN_CONFIDENCE_THRESHOLD:
                                    continue
                                
                                # Check for duplicates
                                center_x = vx1 + x + w_contour // 2
                                center_y = vy1 + y + h_contour // 2
                                is_duplicate = False
                                for prev_region in detected_regions["dent"]:
                                    prev_x, prev_y, prev_frame = prev_region
                                    if abs(prev_x - center_x) < 60 and abs(prev_y - center_y) < 60 and abs(prev_frame - frame_idx) < 3:
                                        is_duplicate = True
                                        break
                                
                                if is_duplicate:
                                    continue
                                
                                # Expand bounding box
                                padding = 40
                                x_expanded = max(0, x - padding)
                                y_expanded = max(0, y - padding)
                                w_expanded = min(vehicle_image.shape[1] - x_expanded, w_contour + 2 * padding)
                                h_expanded = min(vehicle_image.shape[0] - y_expanded, h_contour + 2 * padding)
                                
                                # Crop dent region
                                dent_crop = vehicle_image[y_expanded:y_expanded+h_expanded, x_expanded:x_expanded+w_expanded]
                                
                                if dent_crop.size > 0:
                                    dents_count += 1
                                    snapshot_counter["dent"] += 1
                                    detected_regions["dent"].append((center_x, center_y, frame_idx))
                                    
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
                                        "confidence": confidence,
                                        "bbox": [vx1 + x_expanded, vy1 + y_expanded, vx1 + x_expanded + w_expanded, vy1 + y_expanded + h_expanded],
                                    })

            except Exception as e:
                print(f"Damage detection error for {frame_path}: {e}")
                continue

        # Sort damage locations by confidence (highest first)
        damage_locations.sort(key=lambda x: x.get("confidence", 0), reverse=True)
        
        # Determine severity based on damage count and quality
        total_damage = scratches_count + dents_count + rust_count
        avg_confidence = np.mean([loc.get("confidence", 0) for loc in damage_locations]) if damage_locations else 0
        
        # Severity calculation: consider both count and confidence
        if total_damage == 0:
            severity = "low"
        elif total_damage > 10 or (total_damage > 5 and avg_confidence > 0.6):
            severity = "high"
        elif total_damage > 3 or avg_confidence > 0.5:
            severity = "medium"
        else:
            severity = "low"

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
            "locations": damage_locations[:20],  # Limit to top 20 locations by confidence
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
