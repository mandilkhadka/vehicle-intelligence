"""
Vehicle identification service
Identifies vehicle type, brand, and model using YOLOv8 and CLIP
"""

import asyncio
import logging
import os
from typing import Dict, Any, List, Optional, Tuple
from ultralytics import YOLO
from PIL import Image
import torch
import cv2
import numpy as np
from collections import Counter

logger = logging.getLogger(__name__)


class VehicleIdentifier:
    """Identifies vehicle type, brand, and model"""

    def __init__(self, yolo_model: Optional[YOLO] = None, clip_model=None, clip_processor=None):
        """
        Initialize vehicle identifier with models.

        Args:
            yolo_model: Pre-loaded YOLOv8 model instance (from ModelRegistry)
            clip_model: Pre-loaded CLIP model instance (from ModelRegistry)
            clip_processor: Pre-loaded CLIP processor instance (from ModelRegistry)

        If models are not provided, they will be loaded internally (legacy behavior).
        For best performance, pass pre-loaded models from ModelRegistry.
        """
        # Use injected models or load internally (legacy fallback)
        if yolo_model is not None:
            logger.info("VehicleIdentifier: Using injected YOLOv8 model")
            self.yolo_model = yolo_model
        else:
            logger.warning("VehicleIdentifier: Loading YOLOv8 model internally (consider using ModelRegistry)")
            self.yolo_model = YOLO("yolov8n.pt")

        if clip_model is not None and clip_processor is not None:
            logger.info("VehicleIdentifier: Using injected CLIP model and processor")
            self.clip_model = clip_model
            self.clip_processor = clip_processor
        else:
            logger.warning("VehicleIdentifier: Loading CLIP models internally (consider using ModelRegistry)")
            from transformers import CLIPProcessor, CLIPModel
            os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
            self.clip_model = CLIPModel.from_pretrained(
                "openai/clip-vit-base-patch32",
                local_files_only=False,
                resume_download=True
            )
            self.clip_processor = CLIPProcessor.from_pretrained(
                "openai/clip-vit-base-patch32",
                local_files_only=False,
                resume_download=True
            )

        # Common vehicle brands and models
        self.vehicle_brands = [
            "Toyota", "Honda", "Ford", "Chevrolet", "Nissan",
            "BMW", "Mercedes-Benz", "Audi", "Volkswagen", "Hyundai",
            "Kia", "Mazda", "Subaru", "Jeep", "Lexus",
            "Tesla", "Porsche", "Jaguar", "Land Rover", "Volvo"
        ]

        self.vehicle_types = ["car", "bike", "motorcycle", "truck", "suv"]

    async def identify(self, frame_paths: List[str]) -> Dict[str, Any]:
        """
        Identify vehicle from frames
        Args:
            frame_paths: List of frame image paths
        Returns:
            Dictionary with vehicle type, brand, model, and confidence
        """
        return await asyncio.to_thread(
            self._identify_sync, frame_paths
        )

    def _identify_sync(self, frame_paths: List[str]) -> Dict[str, Any]:
        """
        Synchronous vehicle identification with YOLO result caching (Phase 4 optimization)
        """

        # Use first few frames for identification
        sample_frames = frame_paths[:5] if len(frame_paths) > 5 else frame_paths

        # Phase 4 Optimization: Cache YOLO results to avoid redundant inference
        # Previously: YOLO was called 4+ times (1 in _detect_vehicle_type + 3 in _detect_vehicle_color)
        # Now: YOLO is called once per frame and results are reused
        logger.info(f"VehicleIdentifier: Caching YOLO results for {len(sample_frames)} frames")
        yolo_cache = {}
        for frame_path in sample_frames:
            try:
                yolo_cache[frame_path] = self.yolo_model(frame_path)
            except Exception as e:
                logger.warning(f"YOLO inference failed for {frame_path}: {e}")
                yolo_cache[frame_path] = None

        # Detect vehicle type using cached YOLO results
        vehicle_type = self._detect_vehicle_type_cached(sample_frames[0], yolo_cache)

        # Identify brand and model using CLIP
        brand, model, confidence = self._identify_brand_model(sample_frames)

        # Detect vehicle color using cached YOLO results
        color = self._detect_vehicle_color_cached(sample_frames, yolo_cache)

        return {
            "type": vehicle_type,
            "brand": brand,
            "model": model,
            "color": color,
            "confidence": confidence,
        }

    def _detect_vehicle_type_cached(self, frame_path: str, yolo_cache: Dict[str, Any]) -> str:
        """
        Detect vehicle type using cached YOLO results (Phase 4 optimization)
        """
        try:
            results = yolo_cache.get(frame_path)
            if results is None:
                return "car"  # Default fallback

            # Check for vehicle classes in YOLO results
            # YOLO COCO classes: 2=car, 3=motorcycle, 5=bus, 7=truck
            vehicle_classes = {2: "car", 3: "bike", 7: "truck"}

            for result in results:
                boxes = result.boxes
                if boxes is not None:
                    for box in boxes:
                        class_id = int(box.cls[0])
                        if class_id in vehicle_classes:
                            return vehicle_classes[class_id]

            # Default to car if no vehicle detected
            return "car"
        except Exception as e:
            logger.warning(f"Vehicle type detection error: {e}")
            return "car"  # Default fallback

    def _detect_vehicle_color_cached(self, frame_paths: List[str], yolo_cache: Dict[str, Any]) -> str:
        """
        Detect vehicle color from frames using cached YOLO results (Phase 4 optimization)
        Returns: Color name (e.g., "White", "Black", "Silver", etc.)
        """
        try:
            # Color ranges in HSV (Hue, Saturation, Value)
            color_ranges = {
                "White": ([0, 0, 200], [180, 30, 255]),
                "Black": ([0, 0, 0], [180, 255, 50]),
                "Silver": ([0, 0, 150], [180, 30, 200]),
                "Gray": ([0, 0, 50], [180, 30, 150]),
                "Grey": ([0, 0, 50], [180, 30, 150]),
                "Red": ([0, 100, 50], [10, 255, 255]),  # Also check 170-180
                "Blue": ([100, 100, 50], [130, 255, 255]),
                "Green": ([40, 100, 50], [80, 255, 255]),
                "Brown": ([10, 100, 20], [25, 255, 150]),
                "Beige": ([20, 30, 150], [40, 100, 255]),
                "Gold": ([20, 100, 100], [30, 255, 255]),
                "Yellow": ([20, 100, 100], [40, 255, 255]),
                "Orange": ([10, 100, 100], [25, 255, 255]),
                "Purple": ([130, 100, 50], [160, 255, 255]),
            }

            detected_colors = []

            for frame_path in frame_paths[:3]:  # Use first 3 frames
                try:
                    # Load image
                    image = cv2.imread(frame_path)
                    if image is None:
                        continue

                    # Use cached YOLO results instead of running inference again
                    results = yolo_cache.get(frame_path)
                    vehicle_box = None

                    if results is not None:
                        for result in results:
                            boxes = result.boxes
                            if boxes is not None:
                                for box in boxes:
                                    class_id = int(box.cls[0])
                                    # YOLO COCO classes: 2=car, 3=motorcycle, 7=truck
                                    if class_id in [2, 3, 7]:
                                        # Get bounding box coordinates
                                        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                                        vehicle_box = (int(x1), int(y1), int(x2), int(y2))
                                        break

                    if vehicle_box is None:
                        # If no vehicle detected, use center region of image
                        h, w = image.shape[:2]
                        vehicle_box = (w//4, h//4, 3*w//4, 3*h//4)

                    # Extract vehicle region
                    x1, y1, x2, y2 = vehicle_box
                    vehicle_region = image[y1:y2, x1:x2]

                    if vehicle_region.size == 0:
                        continue

                    # Convert to HSV for better color analysis
                    hsv = cv2.cvtColor(vehicle_region, cv2.COLOR_BGR2HSV)

                    # Sample pixels from vehicle region (avoid edges which might be shadows)
                    h_center, w_center = hsv.shape[0]//2, hsv.shape[1]//2
                    h_margin, w_margin = hsv.shape[0]//4, hsv.shape[1]//4

                    # Sample from center region
                    center_region = hsv[
                        h_center-h_margin:h_center+h_margin,
                        w_center-w_margin:w_center+w_margin
                    ]

                    if center_region.size == 0:
                        center_region = hsv

                    # Reshape for easier processing
                    pixels = center_region.reshape(-1, 3)

                    # Count pixels in each color range
                    color_counts = {}
                    for color_name, (lower, upper) in color_ranges.items():
                        lower_arr = np.array(lower)
                        upper_arr = np.array(upper)

                        # Handle red color which wraps around hue
                        if color_name == "Red":
                            mask1 = cv2.inRange(pixels, np.array([0, 100, 50]), np.array([10, 255, 255]))
                            mask2 = cv2.inRange(pixels, np.array([170, 100, 50]), np.array([180, 255, 255]))
                            mask = mask1 | mask2
                        else:
                            mask = cv2.inRange(pixels, lower_arr, upper_arr)

                        count = np.sum(mask > 0)
                        if count > 0:
                            color_counts[color_name] = count

                    # Get dominant color
                    if color_counts:
                        dominant_color = max(color_counts, key=color_counts.get)
                        detected_colors.append(dominant_color)

                except Exception as e:
                    logger.warning(f"Color detection error for {frame_path}: {e}")
                    continue

            # Return most common color detected
            if detected_colors:
                color_counter = Counter(detected_colors)
                most_common_color = color_counter.most_common(1)[0][0]
                return most_common_color
            else:
                return "Unknown"

        except Exception as e:
            logger.warning(f"Vehicle color detection error: {e}")
            return "Unknown"

    def _identify_brand_model(
        self, frame_paths: List[str]
    ) -> tuple[str, str, float]:
        """
        Identify brand and model using CLIP
        Returns: (brand, model, confidence)
        """
        try:
            # Load and process images
            images = [Image.open(path) for path in frame_paths[:3]]
            
            # Create text prompts for vehicle brands
            brand_texts = [f"a {brand} vehicle" for brand in self.vehicle_brands]
            
            # Process with CLIP
            inputs = self.clip_processor(
                text=brand_texts, images=images, return_tensors="pt", padding=True
            )
            
            # Get embeddings
            outputs = self.clip_model(**inputs)
            logits_per_image = outputs.logits_per_image
            
            # Get best matching brand
            probs = logits_per_image.softmax(dim=1)
            avg_probs = probs.mean(dim=0)
            best_brand_idx = avg_probs.argmax().item()
            confidence = avg_probs[best_brand_idx].item()
            
            best_brand = self.vehicle_brands[best_brand_idx]
            
            # For MVP, use generic model name
            # In production, you'd have a more sophisticated model identification
            model = f"{best_brand} Model"
            
            return best_brand, model, confidence
            
        except Exception as e:
            logger.warning(f"Brand/model identification error: {e}")
            return "Unknown", "Unknown", 0.0

