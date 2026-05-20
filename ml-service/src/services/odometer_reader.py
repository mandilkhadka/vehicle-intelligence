"""
Odometer reading service
Reads odometer values using OCR (Tesseract/PaddleOCR) with Gemini LLM validation
"""

import asyncio
from typing import Dict, Any, List
import base64
import re
import numpy as np
import os
import json
import cv2
import shutil
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

from src.config.env import load_ml_environment
from src.utils.image_quality import read_image_with_orientation, write_jpeg

try:
    from PIL import Image
    import PIL.PngImagePlugin  # noqa: F401 - registers PNG support used by google-generativeai
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# Try to import PaddleOCR, fallback to pytesseract
try:
    from paddleocr import PaddleOCR
    PADDLEOCR_AVAILABLE = True
except ImportError:
    PADDLEOCR_AVAILABLE = False
    try:
        import pytesseract
        TESSERACT_AVAILABLE = PIL_AVAILABLE and shutil.which("tesseract") is not None
    except ImportError:
        TESSERACT_AVAILABLE = False

# Try to import Gemini for validation
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return float(default)
    try:
        return float(raw)
    except ValueError:
        return float(default)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return int(default)
    try:
        return int(raw)
    except ValueError:
        return int(default)


# Env-tunable knobs. Defaults match the previous hardcoded behaviour.
_MAX_OCR_FRAMES = _env_int("ML_ODOMETER_MAX_FRAMES", 3)
_TESSERACT_TIMEOUT_SECONDS = _env_int("ML_TESSERACT_TIMEOUT_SECONDS", 4)
_EARLY_STOP_OCR_CONFIDENCE = _env_float("ML_ODOMETER_EARLY_STOP_CONFIDENCE", 0.86)
_MIN_RELIABLE_LOCAL_OCR_CONFIDENCE = _env_float("ML_ODOMETER_MIN_RELIABLE_CONFIDENCE", 0.50)

# Plausibility bounds. A modern passenger vehicle should never read above ~2M km/mi.
# Use a generous ceiling but reject obvious OCR hallucinations like 99999999.
_MAX_PLAUSIBLE_ODOMETER = _env_int("ML_ODOMETER_MAX_PLAUSIBLE", 2_000_000)
_MIN_PLAUSIBLE_ODOMETER = _env_int("ML_ODOMETER_MIN_PLAUSIBLE", 0)

_LOW_CONFIDENCE_OCR_REASON = (
    "Local OCR produced only low-confidence or conflicting odometer candidates; "
    "manual/VLM verification is required"
)


def _is_plausible_odometer(value) -> bool:
    """Reject obviously bad OCR digits before they reach the user-facing report."""
    try:
        num = int(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return False
    if num < _MIN_PLAUSIBLE_ODOMETER or num > _MAX_PLAUSIBLE_ODOMETER:
        return False
    # Reject runs of identical digits (e.g. 99999999, 88888888) which are
    # classic OCR hallucinations on 7-segment displays.
    s = str(num)
    if len(s) >= 6 and len(set(s)) == 1:
        return False
    return True


class OdometerReader:
    """Reads odometer values from dashboard images using OCR with Gemini LLM validation"""

    def __init__(self):
        """Initialize OCR reader and Gemini LLM"""
        if PADDLEOCR_AVAILABLE:
            print("Initializing PaddleOCR...")
            # Configure PaddleOCR for better number recognition
            self.ocr = PaddleOCR(
                use_angle_cls=True, 
                lang="en",
                det_model_dir=None,  # Use default detection model
                rec_model_dir=None,  # Use default recognition model
                use_gpu=False,  # Set to True if GPU available
                show_log=False
            )
            self.use_paddle = True
        elif TESSERACT_AVAILABLE:
            print("Using Tesseract OCR (PaddleOCR not available)...")
            self.use_paddle = False
            # Configure Tesseract for better number recognition
            self.tesseract_config = r'--oem 3 --psm 6 -c tessedit_char_whitelist=0123456789KM km'
        else:
            print("Warning: No OCR library available. Odometer reading will be limited.")
            self.use_paddle = False
        self.ocr_available = bool(PADDLEOCR_AVAILABLE or TESSERACT_AVAILABLE)
        
        # Initialize Gemini/OpenAI validation if configured.
        load_ml_environment()
        
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if api_key and len(api_key) >= 20 and GEMINI_AVAILABLE:
            try:
                genai.configure(api_key=api_key)
                self.gemini_model = genai.GenerativeModel("gemini-2.5-pro")
                print("Gemini LLM initialized with gemini-2.5-pro for odometer validation")
                self.use_gemini = True
            except Exception as e:
                print(f"Failed to configure Gemini API: {e}")
                self.use_gemini = False
        else:
            self.use_gemini = False
            if not api_key:
                print("Gemini API key not found. Odometer validation will use OCR only.")
            else:
                print("Gemini library not available. Odometer validation will use OCR only.")

        self.openai_client = None
        self.openai_api_key = None
        self.openai_base_url = os.getenv("OPENAI_BASE_URL", "").strip()
        self.openai_model = os.getenv("OPENAI_VISION_MODEL", "gpt-4.1-mini").strip() or "gpt-4.1-mini"
        openai_key = os.getenv("OPENAI_API_KEY", "").strip()
        if (openai_key and len(openai_key) >= 20) or self.openai_base_url:
            try:
                from openai import OpenAI
                client_kwargs = {"api_key": openai_key or "local-openai-compatible"}
                if self.openai_base_url:
                    client_kwargs["base_url"] = self.openai_base_url
                self.openai_client = OpenAI(**client_kwargs)
                self.openai_api_key = client_kwargs["api_key"]
                self.use_openai = True
                print(f"OpenAI fallback initialized with {self.openai_model} for odometer validation")
            except Exception as e:
                print(f"Failed to configure OpenAI odometer fallback: {e}")
                self.use_openai = False
        else:
            self.use_openai = False

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
        Synchronous odometer reading with enhanced preprocessing
        Optimized for single image processing (not video frames)
        """
        if not dashboard_frames:
            return {
                "value": None,
                "confidence": 0.0,
                "speedometer_image_path": None,
            }
        self._last_gemini_error = None
        self._last_openai_error = None

        odometer_values = []
        all_ocr_text_combined = []
        best_confidence = 0.0
        best_image_path = None

        if not self.ocr_available and (self.use_gemini or self.use_openai):
            vlm_reading = self._read_odometer_with_vlm_vision(dashboard_frames)
            if vlm_reading:
                return vlm_reading
            reason = (
                self._last_gemini_error
                or self._last_openai_error
                or "No OCR engine available and VLM vision did not return a reading"
            )
            return {
                "value": None,
                "confidence": 0.0,
                "speedometer_image_path": dashboard_frames[0] if dashboard_frames else None,
                "source": self._vlm_source_label(),
                "reason": reason,
                "reasoning": reason,
            }

        # Process each dashboard frame (typically just one image)
        for frame_path in dashboard_frames[:_MAX_OCR_FRAMES]:
            try:
                # Preprocess image for better OCR
                preprocessed_images = self._preprocess_image(frame_path)
                
                # Try OCR on multiple preprocessed versions
                for preprocessed_path, preprocessing_type in preprocessed_images:
                    try:
                        # Run OCR on preprocessed image
                        if self.use_paddle and PADDLEOCR_AVAILABLE:
                            result = self.ocr.ocr(preprocessed_path, cls=True)
                        elif TESSERACT_AVAILABLE:
                            # Use Tesseract OCR with optimized config
                            image = Image.open(preprocessed_path)
                            # Try multiple PSM modes for better results
                            texts = []
                            configs = (
                                self.tesseract_config,
                                r'--oem 3 --psm 7 -c tessedit_char_whitelist=0123456789KM km',
                                r'--oem 3 --psm 8 -c tessedit_char_whitelist=0123456789',
                            )
                            for config in configs:
                                try:
                                    texts.append(
                                        pytesseract.image_to_string(
                                            image,
                                            config=config,
                                            timeout=_TESSERACT_TIMEOUT_SECONDS,
                                        )
                                    )
                                except RuntimeError as e:
                                    print(f"Tesseract OCR timed out or failed for {preprocessing_type}: {e}")
                            
                            # Combine results
                            combined_text = "\n".join(texts)
                            # Convert to PaddleOCR-like format
                            result = [[(None, (combined_text, 0.8))]] if combined_text.strip() else None
                        else:
                            # No OCR available, skip
                            continue

                        # Extract text and find odometer value
                        if result and result[0]:
                            for line in result[0]:
                                if line and len(line) >= 2:
                                    text = line[1][0]  # Text content
                                    confidence = line[1][1]  # Confidence score
                                    
                                    # Boost confidence for certain preprocessing types
                                    if preprocessing_type == "enhanced":
                                        confidence = min(confidence * 1.1, 1.0)
                                    
                                    all_ocr_text_combined.append({
                                        "text": text, 
                                        "confidence": confidence,
                                        "preprocessing": preprocessing_type
                                    })

                                    # Look for numbers that could be odometer reading
                                    # Odometer typically shows 5-7 digits (kilometers)
                                    # Also try 4-8 digits for flexibility
                                    numbers = re.findall(r"\d{4,8}", text.replace(" ", "").replace(",", "").replace(".", ""))
                                    
                                    # Also look for numbers with "KM" or "km" suffix
                                    km_pattern = re.findall(r"(\d{4,8})\s*(?:KM|km|mi|MI)", text, re.IGNORECASE)
                                    numbers.extend([m[0] for m in km_pattern])

                                    for num_str in numbers:
                                        try:
                                            num_value = int(num_str)
                                            # Reasonable odometer range: 0 to 999,999 km
                                            # Extended to 9,999,999 for newer vehicles
                                            if 0 <= num_value <= 9999999:
                                                # Prefer 5-7 digit numbers (most common)
                                                if 5 <= len(num_str) <= 7:
                                                    confidence_boost = 1.1
                                                else:
                                                    confidence_boost = 1.0
                                                
                                                odometer_values.append({
                                                    "value": num_value,
                                                    "confidence": min(confidence * confidence_boost, 1.0),
                                                    "source_text": text,
                                                    "frame": frame_path,
                                                    "preprocessing": preprocessing_type,
                                                    "digit_count": len(num_str)
                                                })
                                                if confidence > best_confidence:
                                                    best_confidence = confidence
                                                    best_image_path = frame_path
                                        except ValueError:
                                            continue
                    except Exception as e:
                        print(f"OCR error for preprocessed image {preprocessing_type}: {e}")
                        continue
                    
                    # Clean up temporary preprocessed images
                    if preprocessing_type != "original" and os.path.exists(preprocessed_path):
                        try:
                            os.remove(preprocessed_path)
                        except:
                            pass

                if best_confidence >= _EARLY_STOP_OCR_CONFIDENCE:
                    break

            except Exception as e:
                print(f"Image processing error for {frame_path}: {e}")
                continue
        
        # If we found potential readings, validate with Gemini
        if odometer_values and (self.use_gemini or self.use_openai) and all_ocr_text_combined:
            validated = self._validate_ocr_readings_with_vlm(odometer_values, all_ocr_text_combined, best_image_path, dashboard_frames)
            if validated:
                # Replace with validated reading
                odometer_values = [validated]
                best_image_path = validated.get("frame", best_image_path)

        # Deduplicate and prioritize readings
        if odometer_values:
            sorted_readings = self._rank_ocr_readings(odometer_values)
            
            # Use the value with highest confidence (or validated value from Gemini)
            best_reading = sorted_readings[0]
            image_path = best_reading.get("frame") or best_image_path or (dashboard_frames[0] if dashboard_frames else None)
            
            return {
                "value": best_reading["value"],
                "confidence": best_reading.get("confidence", 0.0),
                "speedometer_image_path": image_path,
                "source": "local_ocr",
                "reason": (
                    _LOW_CONFIDENCE_OCR_REASON
                    if best_reading.get("confidence", 0.0) < _MIN_RELIABLE_LOCAL_OCR_CONFIDENCE
                    else None
                ),
                "alternatives": [
                    {
                        "value": item.get("value"),
                        "confidence": item.get("confidence", 0.0),
                        "occurrences": item.get("occurrences", 1),
                        "digit_count": item.get("digit_count"),
                        "preprocessing": item.get("preprocessing"),
                    }
                    for item in sorted_readings[1:6]
                ],
            }
        else:
            if self.use_gemini or self.use_openai:
                vlm_reading = self._read_odometer_with_vlm_vision(dashboard_frames)
                if vlm_reading:
                    return vlm_reading
            return {
                "value": None,
                "confidence": 0.0,
                "speedometer_image_path": dashboard_frames[0] if dashboard_frames else None,
                "source": "local_ocr" if self.ocr_available else "none",
                "reason": "No odometer value returned by local OCR",
            }

    def _read_odometer_with_vlm_vision(self, dashboard_frames: List[str]) -> Dict[str, Any]:
        if self.use_gemini:
            reading = self._read_odometer_with_gemini_vision(dashboard_frames)
            if reading and reading.get("value") is not None:
                return reading
        if self.use_openai:
            reading = self._read_odometer_with_openai_vision(dashboard_frames)
            if reading:
                return reading
        return None

    def _vlm_source_label(self) -> str:
        if self.use_gemini and self.use_openai:
            return "vlm_vision"
        if self.use_gemini:
            return "gemini_vision"
        if self.use_openai:
            return "openai_vision"
        return "none"

    @staticmethod
    def _rank_ocr_readings(odometer_values: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        # Filter out implausible OCR results (e.g. 99999999 hallucinations,
        # negative values, absurd ranges) before scoring. These are usually
        # caused by 7-segment glare or partial digit occlusion.
        odometer_values = [r for r in odometer_values if _is_plausible_odometer(r.get("value"))]
        if not odometer_values:
            return []
        value_groups: Dict[int, Dict[str, Any]] = {}
        for reading in odometer_values:
            value = reading["value"]
            group = value_groups.setdefault(
                value,
                {
                    **reading,
                    "confidence": 0.0,
                    "occurrences": 0,
                    "preprocessing_set": set(),
                    "frames": set(),
                },
            )
            group["occurrences"] += 1
            group["confidence"] = max(group.get("confidence", 0.0), reading.get("confidence", 0.0))
            if reading.get("preprocessing"):
                group["preprocessing_set"].add(reading.get("preprocessing"))
            if reading.get("frame"):
                group["frames"].add(reading.get("frame"))

        total_readings = max(len(odometer_values), 1)
        unique_values = max(len(value_groups), 1)
        ranked = []
        for group in value_groups.values():
            digit_count = group.get("digit_count", len(str(group.get("value", ""))))
            digit_fit = 1.0 - min(abs(digit_count - 6) / 4.0, 1.0)
            support = group["occurrences"] / total_readings
            prep_diversity = min(len(group["preprocessing_set"]) / 3.0, 1.0)
            adjusted_confidence = group["confidence"] * (
                0.35 + (support * 0.35) + (prep_diversity * 0.15) + (digit_fit * 0.15)
            )
            if unique_values > 1 and group["occurrences"] == 1:
                adjusted_confidence = min(adjusted_confidence, 0.42)
            group["confidence"] = round(float(np.clip(adjusted_confidence, 0.0, 1.0)), 4)
            group["preprocessing"] = sorted(group["preprocessing_set"])
            group.pop("preprocessing_set", None)
            group.pop("frames", None)
            ranked.append(group)

        return sorted(
            ranked,
            key=lambda item: (
                item.get("confidence", 0.0),
                item.get("occurrences", 1),
                -abs(item.get("digit_count", 6) - 6),
            ),
            reverse=True,
        )

    def _read_odometer_with_gemini_vision(self, dashboard_frames: List[str]) -> Dict[str, Any]:
        """Use Gemini vision directly when OCR cannot produce a reliable reading."""
        if not self.use_gemini or not PIL_AVAILABLE:
            return None

        readings = []
        unavailable_reason = None
        for frame_path in dashboard_frames[:4]:
            if not frame_path or not os.path.exists(frame_path):
                continue
            try:
                image = Image.open(frame_path).convert("RGB")
                prompt = """Read the vehicle odometer value from this dashboard or instrument-cluster image.

Return ONLY a JSON object in this exact format:
{
  "value": <integer_odometer_value_or_null>,
  "confidence": <number_between_0_and_1>,
  "reasoning": "short note"
}

Rules:
- Read the odometer mileage/kilometer total, not speed, trip, range, gear, clock, or temperature.
- Odometer values are usually 4-8 digits.
- If the odometer is not visible or not readable, return null with low confidence.
- Do not include markdown or any text outside the JSON object."""
                response = self._generate_gemini_content([prompt, image])
                if response is None:
                    unavailable_reason = self._last_gemini_error or unavailable_reason
                    continue
                parsed = self._parse_gemini_odometer_json(getattr(response, "text", ""), frame_path)
                if parsed:
                    readings.append(parsed)
            except Exception as e:
                print(f"Gemini vision odometer error for {frame_path}: {e}")
                continue

        # Drop implausible VLM readings (e.g. 99999999) so they don't trump OCR.
        readings = [r for r in readings if r.get("value") is None or _is_plausible_odometer(r.get("value"))]
        if not readings:
            if unavailable_reason:
                return {
                    "value": None,
                    "confidence": 0.0,
                    "speedometer_image_path": dashboard_frames[0] if dashboard_frames else None,
                    "source": "gemini_vision",
                    "reason": unavailable_reason,
                    "reasoning": unavailable_reason,
                }
            return None

        readings.sort(key=lambda item: item.get("confidence", 0.0), reverse=True)
        best = readings[0]
        return {
            "value": best.get("value"),
            "confidence": best.get("confidence", 0.0),
            "speedometer_image_path": best.get("frame"),
            "source": "gemini_vision",
            "reasoning": best.get("reasoning"),
        }

    def _read_odometer_with_openai_vision(self, dashboard_frames: List[str]) -> Dict[str, Any]:
        """Use OpenAI vision directly when OCR/Gemini cannot produce a reliable reading."""
        if not self.use_openai:
            return None

        prompt = """Read the vehicle odometer value from this dashboard or instrument-cluster image.

Return ONLY a JSON object in this exact format:
{
  "value": <integer_odometer_value_or_null>,
  "confidence": <number_between_0_and_1>,
  "reasoning": "short note"
}

Rules:
- Read the odometer mileage/kilometer total, not speed, trip, range, gear, clock, or temperature.
- Odometer values are usually 4-8 digits.
- If the odometer is not visible or not readable, return null with low confidence.
- Do not include markdown or any text outside the JSON object."""

        readings = []
        unavailable_reason = None
        for frame_path in dashboard_frames[:4]:
            if not frame_path or not os.path.exists(frame_path):
                continue
            response_text = self._generate_openai_content(prompt, [frame_path])
            if response_text is None:
                unavailable_reason = self._last_openai_error or unavailable_reason
                continue
            parsed = self._parse_gemini_odometer_json(response_text, frame_path)
            if parsed:
                readings.append(parsed)

        readings = [r for r in readings if r.get("value") is None or _is_plausible_odometer(r.get("value"))]
        if not readings:
            if unavailable_reason:
                return {
                    "value": None,
                    "confidence": 0.0,
                    "speedometer_image_path": dashboard_frames[0] if dashboard_frames else None,
                    "source": "openai_vision",
                    "reason": unavailable_reason,
                    "reasoning": unavailable_reason,
                }
            return None

        readings.sort(key=lambda item: item.get("confidence", 0.0), reverse=True)
        best = readings[0]
        return {
            "value": best.get("value"),
            "confidence": best.get("confidence", 0.0),
            "speedometer_image_path": best.get("frame"),
            "source": "openai_vision",
            "reasoning": best.get("reasoning"),
        }

    def _generate_gemini_content(self, content):
        """Run Gemini with timeout/retry handling shared by OCR-text and image paths."""
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
        import time

        max_retries = 2
        timeout_seconds = 30
        self._last_gemini_error = None

        for attempt in range(max_retries + 1):
            try:
                executor = ThreadPoolExecutor(max_workers=1)
                try:
                    future = executor.submit(self.gemini_model.generate_content, content)
                    response = future.result(timeout=timeout_seconds)
                finally:
                    executor.shutdown(wait=False, cancel_futures=True)

                if response is None:
                    print(f"Gemini API call returned no response (attempt {attempt + 1}/{max_retries + 1})")
                    if attempt < max_retries:
                        time.sleep(2 ** attempt)
                        continue
                    self._last_gemini_error = "Gemini API unavailable: no response returned"
                    return None
                return response

            except FutureTimeoutError:
                print(f"Gemini API call timed out after {timeout_seconds} seconds (attempt {attempt + 1}/{max_retries + 1})")
                if attempt < max_retries:
                    time.sleep(2 ** attempt)
                    continue
                self._last_gemini_error = f"Gemini API unavailable: timed out after {timeout_seconds} seconds"
                return None

            except Exception as e:
                error_msg = str(e)
                print(f"Gemini API call failed (attempt {attempt + 1}/{max_retries + 1}): {error_msg}")
                normalized_error = error_msg.lower()
                if (
                    "429" in error_msg
                    or "quota" in normalized_error
                    or "rate limit" in normalized_error
                    or "billing" in normalized_error
                ):
                    print("Rate limit exceeded, not retrying")
                    self._last_gemini_error = "Gemini API unavailable: quota, rate limit, or billing cap exceeded"
                    return None
                if "403" in error_msg or "permission" in normalized_error or "invalid" in normalized_error:
                    print("Authentication/permission error, not retrying")
                    self._last_gemini_error = "Gemini API unavailable: authentication or permission error"
                    return None
                if attempt < max_retries:
                    time.sleep(2 ** attempt)
                    continue
                self._last_gemini_error = f"Gemini API unavailable: {error_msg}"
                return None
        return None

    def _generate_openai_content(self, prompt: str, image_paths: List[str] | None = None) -> str | None:
        """Run OpenAI Responses API for odometer validation/vision fallback."""
        import time

        max_retries = 1
        timeout_seconds = 30
        self._last_openai_error = None

        for attempt in range(max_retries + 1):
            try:
                content = [{"type": "input_text", "text": prompt}]
                chat_content = [{"type": "text", "text": prompt}]
                for image_path in image_paths or []:
                    data_url = self._image_data_url(image_path)
                    if data_url:
                        content.append({
                            "type": "input_image",
                            "image_url": data_url,
                            "detail": "high",
                        })
                        chat_content.append({
                            "type": "image_url",
                            "image_url": {"url": data_url, "detail": "high"},
                        })

                response = self._call_openai_responses_api(content, timeout_seconds)
                if response is None:
                    self._last_openai_error = "OpenAI VLM unavailable: no response returned"
                    return None
                text = getattr(response, "output_text", None) or self._extract_openai_output_text(response)
                if not text:
                    self._last_openai_error = "OpenAI VLM unavailable: response returned no text"
                    return None
                return text

            except FutureTimeoutError:
                if attempt < max_retries:
                    time.sleep(2 ** attempt)
                    continue
                self._last_openai_error = f"OpenAI VLM unavailable: timed out after {timeout_seconds} seconds"
                return None
            except Exception as e:
                error_msg = str(e)
                normalized_error = error_msg.lower()
                if any(token in normalized_error for token in ("429", "quota", "rate limit", "billing")):
                    self._last_openai_error = "OpenAI VLM unavailable: quota, rate limit, or billing cap exceeded"
                    return None
                if any(token in normalized_error for token in ("401", "403", "permission", "invalid", "api key")):
                    self._last_openai_error = "OpenAI VLM unavailable: authentication or permission error"
                    return None
                chat_response = self._call_openai_chat_completions(chat_content, timeout_seconds)
                if chat_response is not None:
                    text = getattr(chat_response, "output_text", None) or self._extract_openai_output_text(chat_response)
                    if text:
                        return text
                if attempt < max_retries:
                    time.sleep(2 ** attempt)
                    continue
                self._last_openai_error = f"OpenAI VLM unavailable: {error_msg}"
                return None
        return None

    def _call_openai_responses_api(self, content: List[Dict[str, Any]], timeout_seconds: int):
        executor = ThreadPoolExecutor(max_workers=1)
        try:
            future = executor.submit(
                self.openai_client.responses.create,
                model=self.openai_model,
                input=[{"role": "user", "content": content}],
            )
            return future.result(timeout=timeout_seconds)
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def _call_openai_chat_completions(self, content: List[Dict[str, Any]], timeout_seconds: int):
        try:
            executor = ThreadPoolExecutor(max_workers=1)
            try:
                future = executor.submit(
                    self.openai_client.chat.completions.create,
                    model=self.openai_model,
                    messages=[{"role": "user", "content": content}],
                )
                return future.result(timeout=timeout_seconds)
            finally:
                executor.shutdown(wait=False, cancel_futures=True)
        except Exception:
            return None

    @staticmethod
    def _image_data_url(path: str) -> str | None:
        try:
            with open(path, "rb") as image_file:
                encoded = base64.b64encode(image_file.read()).decode("ascii")
            return f"data:image/jpeg;base64,{encoded}"
        except Exception:
            return None

    @staticmethod
    def _extract_openai_output_text(response: Any) -> str | None:
        choices = getattr(response, "choices", None)
        if isinstance(choices, list) and choices:
            message = getattr(choices[0], "message", None)
            content = getattr(message, "content", None)
            if isinstance(content, str) and content.strip():
                return content

        output = getattr(response, "output", None)
        if not isinstance(output, list):
            return None
        chunks = []
        for item in output:
            content = item.get("content") if isinstance(item, dict) else getattr(item, "content", None)
            if not isinstance(content, list):
                continue
            for block in content:
                text = block.get("text") if isinstance(block, dict) else getattr(block, "text", None)
                if text:
                    chunks.append(str(text))
        return "\n".join(chunks) if chunks else None

    @staticmethod
    def _parse_gemini_odometer_json(response_text: str, frame_path: str) -> Dict[str, Any]:
        response_text = (response_text or "").strip()
        if "```json" in response_text:
            response_text = response_text.split("```json", 1)[1].split("```", 1)[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```", 1)[1].split("```", 1)[0].strip()

        json_start = response_text.find("{")
        json_end = response_text.rfind("}") + 1
        if json_start < 0 or json_end <= json_start:
            return None

        try:
            result = json.loads(response_text[json_start:json_end])
        except json.JSONDecodeError:
            return None

        value = result.get("value")
        if value is None:
            return {
                "value": None,
                "confidence": float(result.get("confidence", 0.0) or 0.0),
                "frame": frame_path,
                "reasoning": result.get("reasoning"),
            }

        try:
            value_int = int(value)
        except (TypeError, ValueError):
            return None

        if not 0 <= value_int <= 9999999:
            return None

        return {
            "value": value_int,
            "confidence": float(result.get("confidence", 0.7) or 0.7),
            "frame": frame_path,
            "reasoning": result.get("reasoning"),
        }
    
    def _validate_ocr_readings_with_vlm(self, ocr_readings: List[Dict], all_ocr_text: List[Dict], best_frame: str, dashboard_frames: List[str]) -> Dict[str, Any]:
        if self.use_gemini:
            validated = self._validate_ocr_readings_with_gemini(ocr_readings, all_ocr_text, best_frame, dashboard_frames)
            if validated:
                return validated
        if self.use_openai:
            return self._validate_ocr_readings_with_openai(ocr_readings, all_ocr_text, best_frame, dashboard_frames)
        return None

    def _odometer_validation_prompt(self, ocr_readings: List[Dict], all_ocr_text: List[Dict]) -> str:
        try:
            # Prepare OCR readings summary with preprocessing info
            readings_summary = []
            for reading in ocr_readings:
                preprocessing = reading.get('preprocessing', 'unknown')
                digit_count = reading.get('digit_count', 'unknown')
                readings_summary.append(
                    f"- Value: {reading['value']} km "
                    f"(confidence: {reading['confidence']:.1%}, "
                    f"digits: {digit_count}, "
                    f"preprocessing: {preprocessing}, "
                    f"from text: '{reading.get('source_text', '')}')"
                )
            
            # Group OCR text by preprocessing type
            text_by_preprocessing = {}
            for item in all_ocr_text:
                prep_type = item.get('preprocessing', 'unknown')
                if prep_type not in text_by_preprocessing:
                    text_by_preprocessing[prep_type] = []
                text_by_preprocessing[prep_type].append(item)
            
            # Prepare all OCR text for context (prioritize enhanced preprocessing)
            all_text_parts = []
            for prep_type in ['enhanced', 'combo', 'upscaled', 'original', 'grayscale']:
                if prep_type in text_by_preprocessing:
                    texts = text_by_preprocessing[prep_type][:5]
                    all_text_parts.append(f"\nFrom {prep_type} preprocessing:")
                    all_text_parts.extend([
                        f"  - '{item['text']}' (confidence: {item['confidence']:.1%})" 
                        for item in texts
                    ])
            
            all_text = "\n".join(all_text_parts) if all_text_parts else "\n".join([
                f"- '{item['text']}' (confidence: {item['confidence']:.1%})" 
                for item in all_ocr_text[:10]
            ])

            return f"""You are an expert at reading vehicle odometer displays from dashboard OCR text.

I have extracted text from a vehicle dashboard image using OCR. The OCR system found the following potential odometer readings:

{chr(10).join(readings_summary)}

Full OCR text extracted from dashboard:
{all_text}

Your task:
1. Analyze the OCR text to identify the actual odometer reading
2. Odometer displays typically show 5-7 digit numbers (kilometers, range 0-999,999)
3. Look for patterns like "ODO", "MILE", "KM", or numbers near speedometer/odometer labels
4. Consider context clues in the surrounding text
5. If multiple readings exist, determine which is most likely the odometer
6. Validate the reading makes sense (not a speed, not a date, etc.)

Return ONLY a JSON object in this exact format (no markdown, no code blocks):
{{
  "value": <corrected_odometer_value_as_integer_or_null>,
  "confidence": <confidence_score_0_to_1>,
  "reasoning": "Brief explanation of how you determined this value"
}}

Important:
- Odometer values are typically 5-7 digits (0 to 999,999 km)
- If the OCR text doesn't contain a clear odometer reading, set value to null
- Be conservative with confidence scores (0.0 to 1.0)
- Consider that OCR may misread: 0/O, 1/I, 5/S, 8/B, etc.
- Return ONLY the JSON object, nothing else before or after"""
        except Exception as e:
            print(f"Odometer validation prompt error: {e}")
            return ""

    def _validate_ocr_readings_with_gemini(self, ocr_readings: List[Dict], all_ocr_text: List[Dict], best_frame: str, dashboard_frames: List[str]) -> Dict[str, Any]:
        """Use Gemini LLM to validate and correct OCR readings based on extracted text"""
        try:
            prompt = self._odometer_validation_prompt(ocr_readings, all_ocr_text)
            if not prompt:
                return None
            response = self._generate_gemini_content(prompt)
            if response is None:
                return None
            
            # Parse JSON response
            response_text = response.text.strip()
            # Remove markdown code blocks if present
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()
            
            # Extract JSON
            json_start = response_text.find("{")
            json_end = response_text.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                result = json.loads(json_str)
                
                # Validate result
                if result.get("value") is not None:
                    value = result.get("value")
                    if isinstance(value, (int, float)) and 0 <= value <= 999999:
                        return {
                            "value": int(value),
                            "confidence": float(result.get("confidence", 0.7)),
                            "frame": best_frame or (dashboard_frames[0] if dashboard_frames else None),
                        }
        except Exception as e:
            print(f"Gemini validation error: {e}")
        
        return None

    def _validate_ocr_readings_with_openai(self, ocr_readings: List[Dict], all_ocr_text: List[Dict], best_frame: str, dashboard_frames: List[str]) -> Dict[str, Any]:
        """Use OpenAI to validate and correct OCR readings based on extracted text."""
        try:
            prompt = self._odometer_validation_prompt(ocr_readings, all_ocr_text)
            if not prompt:
                return None
            response_text = self._generate_openai_content(prompt)
            if response_text is None:
                return None
            parsed = self._parse_gemini_odometer_json(response_text, best_frame or (dashboard_frames[0] if dashboard_frames else None))
            if parsed and parsed.get("value") is not None:
                return {
                    "value": parsed.get("value"),
                    "confidence": parsed.get("confidence", 0.7),
                    "frame": best_frame or (dashboard_frames[0] if dashboard_frames else None),
                }
        except Exception as e:
            print(f"OpenAI validation error: {e}")
        return None
    
    def _preprocess_image(self, image_path: str) -> List[tuple]:
        """
        Preprocess image for better OCR accuracy
        Returns list of (preprocessed_image_path, preprocessing_type) tuples
        """
        preprocessed_images = []
        
        try:
            # Read original image
            image = read_image_with_orientation(image_path)
            if image is None:
                return [(image_path, "original")]
            
            # Get base path for saving preprocessed images
            base_path = Path(image_path)
            base_dir = base_path.parent
            base_name = base_path.stem
            
            # 1. Original image (always include)
            preprocessed_images.append((image_path, "original"))
            
            # 2. Grayscale conversion
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            gray_path = str(base_dir / f"{base_name}_gray.jpg")
            write_jpeg(gray_path, gray)
            preprocessed_images.append((gray_path, "grayscale"))
            
            # 3. Enhanced contrast using CLAHE (Contrast Limited Adaptive Histogram Equalization)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            enhanced = clahe.apply(gray)
            enhanced_path = str(base_dir / f"{base_name}_enhanced.jpg")
            write_jpeg(enhanced_path, enhanced)
            preprocessed_images.append((enhanced_path, "enhanced"))
            
            # 4. Thresholded (binary) image
            _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            thresh_path = str(base_dir / f"{base_name}_thresh.jpg")
            write_jpeg(thresh_path, thresh)
            preprocessed_images.append((thresh_path, "thresholded"))

            # 5. Upscaled image (2x) for better OCR on small text
            height, width = gray.shape
            upscaled = cv2.resize(gray, (width * 2, height * 2), interpolation=cv2.INTER_CUBIC)
            upscaled_path = str(base_dir / f"{base_name}_upscaled.jpg")
            write_jpeg(upscaled_path, upscaled)
            preprocessed_images.append((upscaled_path, "upscaled"))

            # 6. Combination: Enhanced + Denoised
            enhanced_denoised = cv2.fastNlMeansDenoising(enhanced, None, 10, 7, 21)
            combo_path = str(base_dir / f"{base_name}_combo.jpg")
            write_jpeg(combo_path, enhanced_denoised)
            preprocessed_images.append((combo_path, "combo"))
            
        except Exception as e:
            print(f"Image preprocessing error: {e}")
            # Return at least original image
            return [(image_path, "original")]
        
        return preprocessed_images
