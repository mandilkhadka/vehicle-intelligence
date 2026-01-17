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


class VehicleIdentifier:
    """Identifies vehicle type, brand, and model"""

    def __init__(self):
        """Initialize vehicle identifier with models"""
        # Load YOLOv8 model for vehicle type detection
        # Using pretrained COCO model which includes 'car' class
        print("Loading YOLOv8 model for vehicle detection...")
        self.yolo_model = YOLO("yolov8n.pt")  # nano model for speed

        # Load CLIP model for brand/model identification
        print("Loading CLIP model for vehicle identification...")
        self.clip_model = CLIPModel.from_pretrained(
            "openai/clip-vit-base-patch32"
        )
        self.clip_processor = CLIPProcessor.from_pretrained(
            "openai/clip-vit-base-patch32"
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
        Synchronous vehicle identification
        """
        # Use first few frames for identification
        sample_frames = frame_paths[:5] if len(frame_paths) > 5 else frame_paths

        # Detect vehicle type using YOLO
        vehicle_type = self._detect_vehicle_type(sample_frames[0])

        # Identify brand and model using CLIP
        brand, model, confidence = self._identify_brand_model(sample_frames)

        return {
            "type": vehicle_type,
            "brand": brand,
            "model": model,
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
