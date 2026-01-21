"""
Vehicle identification service
Identifies vehicle type, brand, and model using YOLOv8 and CLIP
"""

import asyncio
from typing import Dict, Any, List
from ultralytics import YOLO
from transformers import CLIPProcessor, CLIPModel
from PIL import Image
import torch
import cv2
import numpy as np
from collections import Counter


class VehicleIdentifier:
    """Identifies vehicle type, brand, and model"""

    def __init__(self):
        """Initialize vehicle identifier with models"""
        import time
        import logging
        import os
        from pathlib import Path
        
        logger = logging.getLogger(__name__)
        
        # Load YOLOv8 model for vehicle type detection
        # Using pretrained COCO model which includes 'car' class
        print("Loading YOLOv8 model for vehicle detection...")
        logger.info("Starting YOLOv8 model loading...")
        yolo_start = time.time()
        try:
            self.yolo_model = YOLO("yolov8n.pt")  # nano model for speed
            logger.info(f"YOLOv8 model loaded in {time.time() - yolo_start:.2f}s")
        except Exception as e:
            logger.error(f"Failed to load YOLOv8 model: {e}", exc_info=True)
            raise

        # Load CLIP model for brand/model identification
        print("Loading CLIP model for vehicle identification...")
        logger.info("Starting CLIP model loading (this may take 30-60 seconds on first run)...")
        clip_start = time.time()
        
        # Check if models are cached locally (optional diagnostic)
        try:
            try:
                from transformers.utils import TRANSFORMERS_CACHE
                cache_dir = TRANSFORMERS_CACHE
            except ImportError:
                try:
                    from transformers import file_utils
                    cache_dir = getattr(file_utils, 'default_cache_path', 'unknown')
                except Exception:
                    cache_dir = 'unknown'
            
            model_name = "openai/clip-vit-base-patch32"
            logger.info(f"Transformers cache directory: {cache_dir}")
            logger.info(f"Attempting to load model: {model_name}")
        except Exception as e:
            logger.warning(f"Could not check cache status: {e}")
        
        try:
            logger.info("Loading CLIP model from HuggingFace Hub...")
            # Set environment variable to avoid hanging on network issues
            os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
            
            # Load with explicit timeout handling
            self.clip_model = CLIPModel.from_pretrained(
                "openai/clip-vit-base-patch32",
                local_files_only=False,
                resume_download=True
            )
            logger.info(f"CLIP model loaded in {time.time() - clip_start:.2f}s")
            
            logger.info("Loading CLIP processor...")
            processor_start = time.time()
            self.clip_processor = CLIPProcessor.from_pretrained(
                "openai/clip-vit-base-patch32",
                local_files_only=False,
                resume_download=True
            )
            logger.info(f"CLIP processor loaded in {time.time() - processor_start:.2f}s")
            logger.info(f"Total CLIP initialization time: {time.time() - clip_start:.2f}s")
            
        except Exception as e:
            logger.error(f"Failed to load CLIP model: {e}", exc_info=True)
            logger.error("This might be due to:")
            logger.error("  1. Network connectivity issues")
            logger.error("  2. HuggingFace Hub being unavailable")
            logger.error("  3. Insufficient disk space")
            logger.error("  4. Permission issues with cache directory")
            raise

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
        Synchronous vehicle identification
        """
        # Use first few frames for identification
        sample_frames = frame_paths[:5] if len(frame_paths) > 5 else frame_paths

        # Detect vehicle type using YOLO
        vehicle_type = self._detect_vehicle_type(sample_frames[0])

        # Identify brand and model using CLIP
        brand, model, confidence = self._identify_brand_model(sample_frames)

        # Detect vehicle color
        color = self._detect_vehicle_color(sample_frames)

        return {
            "type": vehicle_type,
            "brand": brand,
            "model": model,
            "color": color,
            "confidence": confidence,
        }

    def _detect_vehicle_type(self, frame_path: str) -> str:
        """
        Detect vehicle type using YOLOv8
        """
        try:
            results = self.yolo_model(frame_path)
            
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
            print(f"Vehicle type detection error: {e}")
            return "car"  # Default fallback

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
            print(f"Brand/model identification error: {e}")
            return "Unknown", "Unknown", 0.0

    def _detect_vehicle_color(self, frame_paths: List[str]) -> str:
        """
        Detect vehicle color from frames
        Returns: Color name (e.g., "White", "Black", "Silver", etc.)
        """
        try:
            # Common vehicle colors
            color_names = [
                "White", "Black", "Silver", "Gray", "Grey", "Red", "Blue",
                "Green", "Brown", "Beige", "Gold", "Yellow", "Orange", "Purple"
            ]
            
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
                    
                    # Detect vehicle bounding box using YOLO
                    results = self.yolo_model(frame_path)
                    vehicle_box = None
                    
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
                    print(f"Color detection error for {frame_path}: {e}")
                    continue
            
            # Return most common color detected
            if detected_colors:
                color_counter = Counter(detected_colors)
                most_common_color = color_counter.most_common(1)[0][0]
                return most_common_color
            else:
                return "Unknown"
                
        except Exception as e:
            print(f"Vehicle color detection error: {e}")
            return "Unknown"
