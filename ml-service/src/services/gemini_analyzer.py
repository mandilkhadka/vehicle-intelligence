"""
Gemini-powered evaluation service.

Sends a handful of representative frames from the uploaded 360° clip to
Gemini 2.5 Pro Vision and asks it to:
  1) Identify the vehicle precisely (make, model, year/generation, variant, color).
  2) Evaluate each individual frame (what it shows + condition observations).
  3) Aggregate damage findings across all frames.
  4) Produce a search query for a brand-new reference image of the same model,
     plus a deterministic Google Images URL the frontend can render.

The output is a single dict shaped for direct consumption by the report generator
and the frontend. All failures degrade gracefully — Gemini is treated as an
augmentation, never a hard dependency.
"""

import asyncio
import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

from PIL import Image

logger = logging.getLogger(__name__)

# How many frames we send to Gemini per request. More = better coverage but
# slower + more tokens. 6 is a reasonable middle ground for 360° walkarounds.
_MAX_FRAMES_TO_SEND = 6

# Per-call timeout. Gemini 2.5 Pro on 6 images typically returns in 15-30s.
_GEMINI_TIMEOUT_SECONDS = 90

# Retries on transient failures (timeouts, 5xx). Auth/quota errors are not retried.
_GEMINI_MAX_RETRIES = 2


class GeminiAnalyzer:
    """Multimodal evaluation of vehicle frames with Gemini 2.5 Pro."""

    def __init__(self) -> None:
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass

        self._genai = None
        self.model = None
        self.api_key: Optional[str] = None

        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key or len(api_key) < 20:
            logger.warning("GeminiAnalyzer: GEMINI_API_KEY missing/invalid — frame evaluation will be skipped")
            return

        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            self._genai = genai
            self.model = genai.GenerativeModel("gemini-2.5-pro")
            self.api_key = api_key
            logger.info("GeminiAnalyzer: initialized with gemini-2.5-pro")
        except Exception as e:
            logger.warning(f"GeminiAnalyzer: failed to initialize Gemini client: {e}")
            self.model = None
            self.api_key = None

    # ------------------------------------------------------------------ #
    # Public API                                                         #
    # ------------------------------------------------------------------ #

    async def analyze(self, frame_paths: List[str]) -> Dict[str, Any]:
        """
        Run Gemini evaluation over the given frames.

        Returns a dict with keys:
          - available: bool — whether Gemini actually ran
          - vehicle: { type, brand, model, year, variant, color, confidence }
          - per_frame: [ { frame, observations, damage_notes, condition } ]
          - damage_findings: aggregated damage summary text
          - condition: overall condition string
          - reference_image: { search_query, search_url, description }
          - raw_summary: free-form summary from Gemini
        """
        return await asyncio.to_thread(self._analyze_sync, frame_paths)

    # ------------------------------------------------------------------ #
    # Sync implementation                                                #
    # ------------------------------------------------------------------ #

    def _analyze_sync(self, frame_paths: List[str]) -> Dict[str, Any]:
        if not self.model or not self.api_key:
            return self._unavailable_response("Gemini API key not configured")

        selected = self._select_frames(frame_paths, _MAX_FRAMES_TO_SEND)
        if not selected:
            return self._unavailable_response("No frames available for Gemini analysis")

        images: List[Image.Image] = []
        used_paths: List[str] = []
        for path in selected:
            try:
                img = Image.open(path).convert("RGB")
                images.append(img)
                used_paths.append(path)
            except Exception as e:
                logger.warning(f"GeminiAnalyzer: skipping unreadable frame {path}: {e}")

        if not images:
            return self._unavailable_response("All selected frames were unreadable")

        prompt = self._build_prompt(used_paths)
        content = [prompt] + images

        response = self._call_with_retries(content)
        if response is None:
            return self._unavailable_response("Gemini call failed after retries")

        try:
            text = response.text or ""
        except Exception as e:
            logger.warning(f"GeminiAnalyzer: response had no text: {e}")
            return self._unavailable_response("Gemini returned no text")

        parsed = self._parse_json_response(text)
        if parsed is None:
            return {
                **self._unavailable_response("Could not parse Gemini JSON"),
                "raw_summary": text[:2000],
            }

        return self._normalize(parsed, used_paths, text)

    # ------------------------------------------------------------------ #
    # Internals                                                          #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _select_frames(frame_paths: List[str], n: int) -> List[str]:
        """Evenly-spaced selection across the clip — gives 360° coverage."""
        if not frame_paths:
            return []
        if len(frame_paths) <= n:
            return list(frame_paths)
        step = len(frame_paths) / n
        return [frame_paths[int(i * step)] for i in range(n)]

    def _build_prompt(self, frame_paths: List[str]) -> str:
        frame_count = len(frame_paths)
        return (
            "You are an expert automotive inspector reviewing frames from a 360° "
            "walkaround video of a single vehicle. The frames are provided in order "
            "below. Each frame is referred to by its 1-based index (1..{n}).\n\n"
            "Carefully examine every frame and produce a STRICT JSON response in the "
            "schema below. Do not include markdown, code fences, or any text outside "
            "the JSON. Use null for unknown values. Be specific — this report will be "
            "shown to a buyer.\n\n"
            "Schema:\n"
            "{{\n"
            '  "vehicle": {{\n'
            '    "type": "car|bike|motorcycle|truck|suv|scooter|other",\n'
            '    "brand": "manufacturer brand, e.g. Honda",\n'
            '    "model": "specific model, e.g. CB350 H\'Ness",\n'
            '    "year": "best-guess model year or generation, e.g. 2022 or 2020-2024",\n'
            '    "variant": "trim/variant if discernible, else null",\n'
            '    "color": "primary exterior color",\n'
            '    "confidence": 0.0-1.0\n'
            '  }},\n'
            '  "per_frame": [\n'
            '    {{\n'
            '      "index": 1,\n'
            '      "view": "front|front-left|left|rear-left|rear|rear-right|right|front-right|dashboard|exhaust|wheel|other",\n'
            '      "observations": "1-3 sentences on what is visible in this specific frame",\n'
            '      "damage_notes": "any scratches, dents, rust, cracks, missing trim, paint issues — or \'none observed\'",\n'
            '      "condition": "excellent|good|fair|poor"\n'
            '    }}\n'
            '  ],\n'
            '  "damage_findings": "Aggregated 2-4 sentence description of all damage observed across frames, with locations.",\n'
            '  "overall_condition": "excellent|good|fair|poor",\n'
            '  "exhaust_observations": "Notes on the exhaust if visible: stock vs aftermarket, tip style, condition. Else null.",\n'
            '  "odometer_observations": "Notes on dashboard/odometer if visible. Else null.",\n'
            '  "reference_image": {{\n'
            '    "description": "one-line description of what a brand-new unit of this exact model looks like",\n'
            '    "search_query": "concise web search query to retrieve an official brand-new product photo of this model (include brand + model + year + \'official\' or \'press image\')"\n'
            '  }},\n'
            '  "summary": "2-3 sentence professional summary of the vehicle and its condition"\n'
            "}}\n\n"
            "Rules:\n"
            "- Provide exactly one per_frame entry per frame, in order, with index 1..{n}.\n"
            "- Be conservative with confidence: if you cannot read the badge, set the brand to your best visual guess and lower confidence.\n"
            "- For damage_notes, do not invent damage that is not visible.\n"
            "- The reference_image.search_query MUST be specific enough to find an official press/marketing photo of a brand-new unit of the SAME model.\n"
        ).format(n=frame_count)

    def _call_with_retries(self, content: List[Any]):
        for attempt in range(_GEMINI_MAX_RETRIES + 1):
            try:
                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(self.model.generate_content, content)
                    response = future.result(timeout=_GEMINI_TIMEOUT_SECONDS)
                if response is None:
                    raise RuntimeError("Gemini returned None")
                return response
            except FutureTimeoutError:
                logger.warning(
                    f"GeminiAnalyzer: timeout after {_GEMINI_TIMEOUT_SECONDS}s "
                    f"(attempt {attempt + 1}/{_GEMINI_MAX_RETRIES + 1})"
                )
            except Exception as e:
                msg = str(e)
                logger.warning(f"GeminiAnalyzer: call failed (attempt {attempt + 1}): {msg}")
                # Don't retry on auth/quota
                lower = msg.lower()
                if any(s in lower for s in ("403", "429", "quota", "permission", "api key", "invalid")):
                    return None
            if attempt < _GEMINI_MAX_RETRIES:
                time.sleep(2 ** attempt)
        return None

    @staticmethod
    def _parse_json_response(text: str) -> Optional[Dict[str, Any]]:
        if not text:
            return None
        # Strip markdown code fences if present
        cleaned = text.strip()
        if cleaned.startswith("```"):
            # remove first fence line
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned
            if cleaned.endswith("```"):
                cleaned = cleaned[: -3]
        # Take the outermost JSON object
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            return json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as e:
            logger.warning(f"GeminiAnalyzer: JSON parse failed: {e}")
            return None

    def _normalize(
        self,
        parsed: Dict[str, Any],
        used_paths: List[str],
        raw_text: str,
    ) -> Dict[str, Any]:
        vehicle = parsed.get("vehicle") or {}
        ref = parsed.get("reference_image") or {}

        # Attach the actual frame path to each per-frame entry so the frontend
        # can show the image alongside Gemini's note.
        per_frame_in = parsed.get("per_frame") or []
        per_frame_out: List[Dict[str, Any]] = []
        for i, path in enumerate(used_paths):
            entry = per_frame_in[i] if i < len(per_frame_in) else {}
            per_frame_out.append({
                "index": i + 1,
                "frame": path,
                "view": entry.get("view"),
                "observations": entry.get("observations"),
                "damage_notes": entry.get("damage_notes"),
                "condition": entry.get("condition"),
            })

        # Build a deterministic Google Images search URL from the query Gemini
        # produced. If the query is missing, synthesize one from the brand/model.
        search_query = (ref.get("search_query") or "").strip()
        if not search_query:
            parts = [
                str(vehicle.get("brand") or "").strip(),
                str(vehicle.get("model") or "").strip(),
                str(vehicle.get("year") or "").strip(),
                "official press image",
            ]
            search_query = " ".join(p for p in parts if p).strip() or "vehicle official press image"

        search_url = f"https://www.google.com/search?tbm=isch&q={quote_plus(search_query)}"

        return {
            "available": True,
            "vehicle": {
                "type": vehicle.get("type"),
                "brand": vehicle.get("brand"),
                "model": vehicle.get("model"),
                "year": vehicle.get("year"),
                "variant": vehicle.get("variant"),
                "color": vehicle.get("color"),
                "confidence": _safe_float(vehicle.get("confidence")),
            },
            "per_frame": per_frame_out,
            "damage_findings": parsed.get("damage_findings"),
            "overall_condition": parsed.get("overall_condition"),
            "exhaust_observations": parsed.get("exhaust_observations"),
            "odometer_observations": parsed.get("odometer_observations"),
            "reference_image": {
                "description": ref.get("description"),
                "search_query": search_query,
                "search_url": search_url,
            },
            "summary": parsed.get("summary"),
            "raw_summary": raw_text[:2000],
        }

    @staticmethod
    def _unavailable_response(reason: str) -> Dict[str, Any]:
        return {
            "available": False,
            "reason": reason,
            "vehicle": None,
            "per_frame": [],
            "damage_findings": None,
            "overall_condition": None,
            "exhaust_observations": None,
            "odometer_observations": None,
            "reference_image": None,
            "summary": None,
        }


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
