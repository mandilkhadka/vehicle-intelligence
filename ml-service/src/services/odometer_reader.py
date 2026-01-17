"""
Odometer reading service
Reads odometer values using OCR (PaddleOCR)
"""

import asyncio
from typing import Dict, Any, List
from paddleocr import PaddleOCR
import re
import numpy as np


class OdometerReader:
    """Reads odometer values from dashboard images using OCR"""

    def __init__(self):
        """Initialize OCR reader"""
        print("Initializing PaddleOCR...")
        # Initialize PaddleOCR
        # use_angle_cls=True enables text direction classification
        self.ocr = PaddleOCR(use_angle_cls=True, lang="en")

    async def read(self, dashboard_frames: List[str]) -> Dict[str, Any]:
        """
        Read odometer value from dashboard frames
        Args:
            dashboard_frames: List of dashboard image paths
        Returns:
            Dictionary with odometer value, confidence, and image path
        """
        return await asyncio.to_thread(self._read_sync, dashboard_frames)

    def _read_sync(self, dashboard_frames: List[str]) -> Dict[str, Any]:
        """
        Synchronous odometer reading
        """
        if not dashboard_frames:
            return {
                "value": None,
                "confidence": 0.0,
                "speedometer_image_path": None,
            }

        odometer_values = []
        best_confidence = 0.0
        best_image_path = None

        # Process each dashboard frame
        for frame_path in dashboard_frames:
            try:
                # Run OCR on dashboard image
                result = self.ocr.ocr(frame_path, cls=True)

                # Extract text and find odometer value
                if result and result[0]:
                    for line in result[0]:
                        if line and len(line) >= 2:
                            text = line[1][0]  # Text content
                            confidence = line[1][1]  # Confidence score

                            # Look for numbers that could be odometer reading
                            # Odometer typically shows 5-7 digits (kilometers)
                            numbers = re.findall(r"\d{5,7}", text.replace(" ", ""))

                            for num_str in numbers:
                                try:
                                    num_value = int(num_str)
                                    # Reasonable odometer range: 0 to 999,999 km
                                    if 0 <= num_value <= 999999:
                                        odometer_values.append(
                                            {"value": num_value, "confidence": confidence}
                                        )
                                        if confidence > best_confidence:
                                            best_confidence = confidence
                                            best_image_path = frame_path
                                except ValueError:
                                    continue

            except Exception as e:
                print(f"OCR error for {frame_path}: {e}")
                continue

        # Get most common value or average
        if odometer_values:
            # Use the value with highest confidence
            best_reading = max(odometer_values, key=lambda x: x["confidence"])
            image_path = best_image_path or (dashboard_frames[0] if dashboard_frames else None)
            return {
                "value": best_reading["value"],
                "confidence": best_reading["confidence"],
                "speedometer_image_path": image_path,
            }
        else:
            return {
                "value": None,
                "confidence": 0.0,
                "speedometer_image_path": dashboard_frames[0] if dashboard_frames else None,
            }
