"""
Odometer reading service
Reads odometer values using OCR (Tesseract/PaddleOCR) with Gemini LLM validation
"""

import asyncio
from typing import Dict, Any, List
import re
import numpy as np
import os
import json
import cv2
from pathlib import Path

# Try to import PaddleOCR, fallback to pytesseract
try:
    from paddleocr import PaddleOCR
    PADDLEOCR_AVAILABLE = True
except ImportError:
    PADDLEOCR_AVAILABLE = False
    try:
        import pytesseract
        from PIL import Image
        TESSERACT_AVAILABLE = True
    except ImportError:
        TESSERACT_AVAILABLE = False

# Try to import Gemini for validation
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False


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
        
        # Initialize Gemini for validation if available
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass
        
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if api_key and len(api_key) >= 20 and GEMINI_AVAILABLE:
            try:
                genai.configure(api_key=api_key)
                # Try gemini-1.5-flash first (faster, more stable), fallback to gemini-1.5-pro
                try:
                    self.gemini_model = genai.GenerativeModel("gemini-1.5-flash")
                    print("Gemini LLM initialized with gemini-1.5-flash for odometer validation")
                except Exception as e:
                    print(f"Failed to initialize gemini-1.5-flash, trying gemini-1.5-pro: {e}")
                    try:
                        self.gemini_model = genai.GenerativeModel("gemini-1.5-pro")
                        print("Gemini LLM initialized with gemini-1.5-pro for odometer validation")
                    except Exception as e2:
                        print(f"Failed to initialize gemini-1.5-pro, trying legacy gemini-pro: {e2}")
                        self.gemini_model = genai.GenerativeModel("gemini-pro")
                        print("Gemini LLM initialized with legacy gemini-pro for odometer validation")
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

        odometer_values = []
        all_ocr_text_combined = []
        best_confidence = 0.0
        best_image_path = None

        # Process each dashboard frame (typically just one image)
        for frame_path in dashboard_frames:
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
                            confidences = []
                            
                            # PSM 6: Assume uniform block of text
                            text1 = pytesseract.image_to_string(image, config=self.tesseract_config)
                            texts.append(text1)
                            
                            # PSM 7: Treat image as single text line
                            config_line = r'--oem 3 --psm 7 -c tessedit_char_whitelist=0123456789KM km'
                            text2 = pytesseract.image_to_string(image, config=config_line)
                            texts.append(text2)
                            
                            # PSM 8: Treat image as single word
                            config_word = r'--oem 3 --psm 8 -c tessedit_char_whitelist=0123456789'
                            text3 = pytesseract.image_to_string(image, config=config_word)
                            texts.append(text3)
                            
                            # Combine results
                            combined_text = "\n".join(texts)
                            # Convert to PaddleOCR-like format
                            result = [[(None, (combined_text, 0.8))]]
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

            except Exception as e:
                print(f"Image processing error for {frame_path}: {e}")
                continue
        
        # If we found potential readings, validate with Gemini
        if odometer_values and self.use_gemini and all_ocr_text_combined:
            validated = self._validate_ocr_readings_with_gemini(odometer_values, all_ocr_text_combined, best_image_path, dashboard_frames)
            if validated:
                # Replace with validated reading
                odometer_values = [validated]
                best_image_path = validated.get("frame", best_image_path)

        # Deduplicate and prioritize readings
        if odometer_values:
            # Group by value and take best confidence for each
            value_groups = {}
            for reading in odometer_values:
                value = reading["value"]
                if value not in value_groups or reading["confidence"] > value_groups[value]["confidence"]:
                    value_groups[value] = reading
            
            # Sort by confidence and digit count (prefer 5-7 digits)
            sorted_readings = sorted(
                value_groups.values(),
                key=lambda x: (
                    x.get("confidence", 0),
                    -abs(x.get("digit_count", 6) - 6)  # Prefer 6 digits (most common)
                ),
                reverse=True
            )
            
            # Use the value with highest confidence (or validated value from Gemini)
            best_reading = sorted_readings[0]
            image_path = best_reading.get("frame") or best_image_path or (dashboard_frames[0] if dashboard_frames else None)
            
            return {
                "value": best_reading["value"],
                "confidence": best_reading.get("confidence", 0.0),
                "speedometer_image_path": image_path,
            }
        else:
            return {
                "value": None,
                "confidence": 0.0,
                "speedometer_image_path": dashboard_frames[0] if dashboard_frames else None,
            }
    
    def _validate_ocr_readings_with_gemini(self, ocr_readings: List[Dict], all_ocr_text: List[Dict], best_frame: str, dashboard_frames: List[str]) -> Dict[str, Any]:
        """Use Gemini LLM to validate and correct OCR readings based on extracted text"""
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
            
            prompt = f"""You are an expert at reading vehicle odometer displays from dashboard OCR text.

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

            # Generate content with timeout and retry logic (30 seconds timeout, 2 retries)
            from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
            import time
            
            max_retries = 2
            timeout_seconds = 30
            
            for attempt in range(max_retries + 1):
                try:
                    with ThreadPoolExecutor(max_workers=1) as executor:
                        future = executor.submit(self.gemini_model.generate_content, prompt)
                        response = future.result(timeout=timeout_seconds)
                    
                    if response is None:
                        print(f"Gemini API call returned no response (attempt {attempt + 1}/{max_retries + 1})")
                        if attempt < max_retries:
                            time.sleep(2 ** attempt)  # Exponential backoff: 1s, 2s
                            continue
                        return None
                    
                    # Success - break out of retry loop
                    break
                    
                except FutureTimeoutError:
                    print(f"Gemini API call timed out after {timeout_seconds} seconds (attempt {attempt + 1}/{max_retries + 1})")
                    if attempt < max_retries:
                        time.sleep(2 ** attempt)  # Exponential backoff
                        continue
                    return None
                    
                except Exception as e:
                    error_msg = str(e)
                    print(f"Gemini API call failed (attempt {attempt + 1}/{max_retries + 1}): {error_msg}")
                    
                    # Check for specific error types that shouldn't be retried
                    if "429" in error_msg or "quota" in error_msg.lower() or "rate limit" in error_msg.lower():
                        print("Rate limit exceeded, not retrying")
                        return None
                    if "403" in error_msg or "permission" in error_msg.lower() or "invalid" in error_msg.lower():
                        print("Authentication/permission error, not retrying")
                        return None
                    
                    if attempt < max_retries:
                        time.sleep(2 ** attempt)  # Exponential backoff
                        continue
                    return None
            else:
                # All retries exhausted
                print("Gemini API call failed after all retries")
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
    
    def _preprocess_image(self, image_path: str) -> List[tuple]:
        """
        Preprocess image for better OCR accuracy
        Returns list of (preprocessed_image_path, preprocessing_type) tuples
        """
        preprocessed_images = []
        
        try:
            # Read original image
            image = cv2.imread(image_path)
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
            cv2.imwrite(gray_path, gray)
            preprocessed_images.append((gray_path, "grayscale"))
            
            # 3. Enhanced contrast using CLAHE (Contrast Limited Adaptive Histogram Equalization)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            enhanced = clahe.apply(gray)
            enhanced_path = str(base_dir / f"{base_name}_enhanced.jpg")
            cv2.imwrite(enhanced_path, enhanced)
            preprocessed_images.append((enhanced_path, "enhanced"))
            
            # 4. Denoised image
            denoised = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)
            denoised_path = str(base_dir / f"{base_name}_denoised.jpg")
            cv2.imwrite(denoised_path, denoised)
            preprocessed_images.append((denoised_path, "denoised"))
            
            # 5. Sharpened image
            kernel = np.array([[-1, -1, -1],
                              [-1,  9, -1],
                              [-1, -1, -1]])
            sharpened = cv2.filter2D(gray, -1, kernel)
            sharpened_path = str(base_dir / f"{base_name}_sharpened.jpg")
            cv2.imwrite(sharpened_path, sharpened)
            preprocessed_images.append((sharpened_path, "sharpened"))
            
            # 6. Thresholded (binary) image
            _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            thresh_path = str(base_dir / f"{base_name}_thresh.jpg")
            cv2.imwrite(thresh_path, thresh)
            preprocessed_images.append((thresh_path, "thresholded"))
            
            # 7. Adaptive threshold
            adaptive_thresh = cv2.adaptiveThreshold(
                gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                cv2.THRESH_BINARY, 11, 2
            )
            adaptive_path = str(base_dir / f"{base_name}_adaptive.jpg")
            cv2.imwrite(adaptive_path, adaptive_thresh)
            preprocessed_images.append((adaptive_path, "adaptive_thresh"))
            
            # 8. Morphological operations to clean up
            kernel_morph = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
            morph = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel_morph)
            morph_path = str(base_dir / f"{base_name}_morph.jpg")
            cv2.imwrite(morph_path, morph)
            preprocessed_images.append((morph_path, "morphological"))
            
            # 9. Upscaled image (2x) for better OCR on small text
            height, width = gray.shape
            upscaled = cv2.resize(gray, (width * 2, height * 2), interpolation=cv2.INTER_CUBIC)
            upscaled_path = str(base_dir / f"{base_name}_upscaled.jpg")
            cv2.imwrite(upscaled_path, upscaled)
            preprocessed_images.append((upscaled_path, "upscaled"))
            
            # 10. Combination: Enhanced + Denoised
            enhanced_denoised = cv2.fastNlMeansDenoising(enhanced, None, 10, 7, 21)
            combo_path = str(base_dir / f"{base_name}_combo.jpg")
            cv2.imwrite(combo_path, enhanced_denoised)
            preprocessed_images.append((combo_path, "combo"))
            
        except Exception as e:
            print(f"Image preprocessing error: {e}")
            # Return at least original image
            return [(image_path, "original")]
        
        return preprocessed_images
