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
import base64
import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

from PIL import Image
import PIL.PngImagePlugin  # noqa: F401 - registers PNG support used by google-generativeai

from src.config.env import load_ml_environment

logger = logging.getLogger(__name__)

# How many organized frames we send to Gemini per request. The frame organizer
# has already reduced the video to representative angles, so 12 covers the
# eight exterior views plus interior, dashboard, odometer, and one spare
# dashboard/detail candidate without sending the whole clip.
_MAX_FRAMES_TO_SEND = 12

# Per-call timeout. Gemini 2.5 Pro on 6 images typically returns in 15-30s.
_GEMINI_TIMEOUT_SECONDS = 90

# Retries on transient failures (timeouts, 5xx). Auth/quota errors are not retried.
_GEMINI_MAX_RETRIES = 2

_OPENAI_TIMEOUT_SECONDS = 90
_OPENAI_MAX_RETRIES = 1


class GeminiAnalyzer:
    """Multimodal evaluation of vehicle frames with Gemini 2.5 Pro."""

    def __init__(self) -> None:
        load_ml_environment()

        self._genai = None
        self.model = None
        self.api_key: Optional[str] = None
        self.openai_client = None
        self.openai_api_key: Optional[str] = None
        self.openai_base_url = os.getenv("OPENAI_BASE_URL", "").strip()
        self.openai_model = os.getenv("OPENAI_VISION_MODEL", "gpt-4.1-mini").strip() or "gpt-4.1-mini"
        self._last_gemini_error: Optional[str] = None
        self._last_openai_error: Optional[str] = None

        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key or len(api_key) < 20:
            logger.warning("GeminiAnalyzer: GEMINI_API_KEY missing/invalid — frame evaluation will be skipped")
        else:
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

        openai_key = os.getenv("OPENAI_API_KEY", "").strip()
        if (openai_key and len(openai_key) >= 20) or self.openai_base_url:
            try:
                from openai import OpenAI
                client_kwargs = {"api_key": openai_key or "local-openai-compatible"}
                if self.openai_base_url:
                    client_kwargs["base_url"] = self.openai_base_url
                self.openai_client = OpenAI(**client_kwargs)
                self.openai_api_key = client_kwargs["api_key"]
                logger.info("GeminiAnalyzer: initialized OpenAI vision fallback with %s", self.openai_model)
            except Exception as e:
                logger.warning("GeminiAnalyzer: failed to initialize OpenAI fallback: %s", e)
                self.openai_client = None
                self.openai_api_key = None

    # ------------------------------------------------------------------ #
    # Public API                                                         #
    # ------------------------------------------------------------------ #

    async def analyze(self, frame_paths: List[str], frame_analysis: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
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
        return await asyncio.to_thread(self._analyze_sync, frame_paths, frame_analysis)

    # ------------------------------------------------------------------ #
    # Sync implementation                                                #
    # ------------------------------------------------------------------ #

    def _analyze_sync(self, frame_paths: List[str], frame_analysis: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if (not self.model or not self.api_key) and (not self.openai_client or not self.openai_api_key):
            return self._unavailable_response("No Gemini or OpenAI VLM API key configured")

        selected_with_labels = self._select_frames(frame_paths, _MAX_FRAMES_TO_SEND, frame_analysis)
        selected = [item["frame"] for item in selected_with_labels]
        if not selected:
            return self._unavailable_response("No frames available for Gemini analysis")

        images: List[Image.Image] = []
        used_selection: List[Dict[str, Any]] = []
        for item in selected_with_labels:
            path = item["frame"]
            try:
                img = Image.open(path).convert("RGB")
                images.append(img)
                used_selection.append(item)
            except Exception as e:
                logger.warning(f"GeminiAnalyzer: skipping unreadable frame {path}: {e}")

        if not images:
            return self._unavailable_response("All selected frames were unreadable")

        prompt = self._build_prompt(used_selection)
        content = [prompt] + images

        response = self._call_with_retries(content) if self.model and self.api_key else None
        if response is None and self.openai_client and self.openai_api_key:
            openai_result = self._analyze_with_openai(prompt, used_selection)
            if openai_result is not None:
                return openai_result

        if response is None:
            reasons = [
                self._last_gemini_error or "Gemini API key not configured",
                self._last_openai_error,
            ]
            reason = "; ".join(str(item) for item in reasons if item)
            return self._unavailable_response(reason or "VLM call failed after retries")

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

        return self._normalize(parsed, used_selection, text, provider="gemini")

    # ------------------------------------------------------------------ #
    # Internals                                                          #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _select_frames(
        frame_paths: List[str],
        n: int,
        frame_analysis: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Prefer organizer-selected views, then fall back to even spacing."""
        selected: List[Dict[str, Any]] = []
        seen: set[str] = set()

        if frame_analysis:
            angle_shots = frame_analysis.get("angle_shots") or {}
            preferred_views = (
                "front", "front-left", "left", "rear-left", "rear",
                "rear-right", "right", "front-right", "interior", "dashboard", "odometer",
            )
            for view in preferred_views:
                entry = angle_shots.get(view) or {}
                path = entry.get("organized_path") or entry.get("frame")
                if path and path not in seen:
                    selected.append(GeminiAnalyzer._selection_payload(path, view, entry))
                    seen.add(path)
                    if len(selected) >= n:
                        return selected

            for entry in frame_analysis.get("dashboard_candidates") or []:
                path = entry.get("organized_path") or entry.get("frame")
                if path and path not in seen:
                    candidate_view = entry.get("view") or "dashboard"
                    selected.append(GeminiAnalyzer._selection_payload(path, f"{candidate_view}_candidate", entry))
                    seen.add(path)
                    if len(selected) >= n:
                        return selected

        remaining = [p for p in frame_paths if p not in seen]
        if not remaining:
            return selected

        slots = max(n - len(selected), 0)
        if slots <= 0:
            return selected
        if len(remaining) <= slots:
            selected.extend({"frame": p, "view": None} for p in remaining)
            return selected

        step = len(remaining) / slots
        selected.extend({"frame": remaining[int(i * step)], "view": None} for i in range(slots))
        return selected

    @staticmethod
    def _selection_payload(path: str, view: Optional[str], source: Dict[str, Any]) -> Dict[str, Any]:
        payload = {"frame": path, "view": view}
        for key in (
            "frame_index",
            "extracted_index",
            "source_frame_index",
            "timestamp_seconds",
            "score",
            "quality_score",
            "vehicle_ratio",
            "dashboard_score",
            "clip_score",
            "temporal_score",
            "high_confidence",
            "semantic_source",
            "candidate_role",
        ):
            if source.get(key) is not None:
                payload[key] = source.get(key)
        return payload

    @staticmethod
    def _build_prompt(selected_frames: List[Dict[str, Any]]) -> str:
        frame_count = len(selected_frames)
        label_lines = []
        for idx, item in enumerate(selected_frames):
            label = item.get("view")
            metadata = []
            if item.get("extracted_index") is not None:
                metadata.append(f"extracted_index={item.get('extracted_index')}")
            if item.get("source_frame_index") is not None:
                metadata.append(f"source_frame_index={item.get('source_frame_index')}")
            if item.get("timestamp_seconds") is not None:
                metadata.append(f"timestamp_seconds={item.get('timestamp_seconds')}")
            if item.get("quality_score") is not None:
                metadata.append(f"quality_score={item.get('quality_score')}")
            if item.get("score") is not None:
                metadata.append(f"selection_score={item.get('score')}")
            if item.get("high_confidence") is not None:
                metadata.append(f"high_confidence={item.get('high_confidence')}")
            if item.get("semantic_source") is not None:
                metadata.append(f"semantic_source={item.get('semantic_source')}")
            if item.get("candidate_role") is not None:
                metadata.append(f"candidate_role={item.get('candidate_role')}")
            suffix = f", {', '.join(metadata)}" if metadata else ""
            label_lines.append(f"- Frame {idx + 1}: organizer_expected_view={label or 'unknown'}{suffix}")
        labels_text = "\n".join(label_lines)
        return (
            "You are an expert automotive inspector reviewing frames from a 360° "
            "walkaround video of a single vehicle. The frames are provided in order "
            "below. Each frame is referred to by its 1-based index (1..{n}).\n\n"
            "The video-understanding preprocessor selected these representative "
            "frames and expected views:\n{labels}\n\n"
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
            '      "view": "front|front-left|left|rear-left|rear|rear-right|right|front-right|interior|dashboard|odometer|exhaust|wheel|other",\n'
            '      "observations": "1-3 sentences on what is visible in this specific frame",\n'
            '      "damage_notes": "any scratches, dents, rust, cracks, missing trim, paint issues — or \'none observed\'",\n'
            '      "condition": "excellent|good|fair|poor"\n'
            '    }}\n'
            '  ],\n'
            '  "damage_findings": "Aggregated 2-4 sentence description of all damage observed across frames, with locations.",\n'
            '  "damage_items": [\n'
            '    {{\n'
            '      "type": "scratch|dent|rust|crack|paint_damage|missing_part|other",\n'
            '      "location": "specific vehicle area, e.g. front bumper, left door, rear fender",\n'
            '      "severity": "low|moderate|high",\n'
            '      "frame_index": 1,\n'
            '      "confidence": 0.0-1.0,\n'
            '      "notes": "short evidence-based description"\n'
            '    }}\n'
            '  ],\n'
            '  "overall_condition": "excellent|good|fair|poor",\n'
            '  "modification_findings": "Stock-vs-modified assessment covering wheels, body kit, lights, exhaust, suspension, paint/wrap, interior electronics. Else null.",\n'
            '  "modification_items": [\n'
            '    {{\n'
            '      "part": "wheels|exhaust|lights|body|suspension|paint_or_wrap|interior|other",\n'
            '      "status": "stock|modified|unknown",\n'
            '      "frame_index": 1,\n'
            '      "confidence": 0.0-1.0,\n'
            '      "notes": "short evidence-based description"\n'
            '    }}\n'
            '  ],\n'
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
            "- For damage_notes and damage_items, do not invent damage that is not visible; return an empty list when none is visible.\n"
            "- For modification_items, only mark modified when visual evidence supports it; otherwise use stock or unknown with low confidence.\n"
            "- The reference_image.search_query MUST be specific enough to find an official press/marketing photo of a brand-new unit of the SAME model.\n"
        ).format(n=frame_count, labels=labels_text)

    def _call_with_retries(self, content: List[Any]):
        self._last_gemini_error = None
        for attempt in range(_GEMINI_MAX_RETRIES + 1):
            try:
                executor = ThreadPoolExecutor(max_workers=1)
                try:
                    future = executor.submit(self.model.generate_content, content)
                    response = future.result(timeout=_GEMINI_TIMEOUT_SECONDS)
                finally:
                    executor.shutdown(wait=False, cancel_futures=True)
                if response is None:
                    raise RuntimeError("Gemini returned None")
                return response
            except FutureTimeoutError:
                logger.warning(
                    f"GeminiAnalyzer: timeout after {_GEMINI_TIMEOUT_SECONDS}s "
                    f"(attempt {attempt + 1}/{_GEMINI_MAX_RETRIES + 1})"
                )
                self._last_gemini_error = (
                    f"Gemini API unavailable: timed out after {_GEMINI_TIMEOUT_SECONDS} seconds"
                )
            except Exception as e:
                msg = str(e)
                logger.warning(f"GeminiAnalyzer: call failed (attempt {attempt + 1}): {msg}")
                # Don't retry on auth/quota
                lower = msg.lower()
                if any(s in lower for s in ("429", "quota", "rate limit", "billing")):
                    self._last_gemini_error = (
                        "Gemini API unavailable: quota, rate limit, or billing cap exceeded"
                    )
                    return None
                if any(s in lower for s in ("403", "permission", "api key", "invalid")):
                    self._last_gemini_error = (
                        "Gemini API unavailable: authentication or permission error"
                    )
                    return None
                self._last_gemini_error = f"Gemini API unavailable: {msg}"
            if attempt < _GEMINI_MAX_RETRIES:
                time.sleep(2 ** attempt)
        return None

    def _analyze_with_openai(
        self,
        prompt: str,
        used_selection: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        response = self._call_openai_with_retries(prompt, used_selection)
        if response is None:
            return None

        text = getattr(response, "output_text", None) or self._extract_openai_output_text(response)
        if not text:
            self._last_openai_error = "OpenAI VLM unavailable: response returned no text"
            return None

        parsed = self._parse_json_response(text)
        if parsed is None:
            self._last_openai_error = "OpenAI VLM unavailable: could not parse JSON"
            return None

        return self._normalize(parsed, used_selection, text, provider="openai")

    def _call_openai_with_retries(self, prompt: str, used_selection: List[Dict[str, Any]]):
        self._last_openai_error = None
        for attempt in range(_OPENAI_MAX_RETRIES + 1):
            try:
                content = [{"type": "input_text", "text": prompt}]
                chat_content = [{"type": "text", "text": prompt}]
                for item in used_selection:
                    data_url = self._image_data_url(item["frame"])
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
                if len(content) == 1:
                    self._last_openai_error = "OpenAI VLM unavailable: no readable images"
                    return None

                response = self._call_openai_responses_api(content)
                if response is None:
                    raise RuntimeError("OpenAI returned None")
                return response
            except FutureTimeoutError:
                self._last_openai_error = (
                    f"OpenAI VLM unavailable: timed out after {_OPENAI_TIMEOUT_SECONDS} seconds"
                )
            except Exception as e:
                msg = str(e)
                logger.warning("GeminiAnalyzer: OpenAI fallback failed (attempt %d): %s", attempt + 1, msg)
                lower = msg.lower()
                if any(s in lower for s in ("429", "quota", "rate limit", "billing")):
                    self._last_openai_error = "OpenAI VLM unavailable: quota, rate limit, or billing cap exceeded"
                    return None
                if any(s in lower for s in ("401", "403", "permission", "api key", "invalid")):
                    self._last_openai_error = "OpenAI VLM unavailable: authentication or permission error"
                    return None
                chat_response = self._call_openai_chat_completions(chat_content)
                if chat_response is not None:
                    return chat_response
                self._last_openai_error = f"OpenAI VLM unavailable: {msg}"
            if attempt < _OPENAI_MAX_RETRIES:
                time.sleep(2 ** attempt)
        return None

    def _call_openai_responses_api(self, content: List[Dict[str, Any]]):
        executor = ThreadPoolExecutor(max_workers=1)
        try:
            future = executor.submit(
                self.openai_client.responses.create,
                model=self.openai_model,
                input=[{"role": "user", "content": content}],
            )
            return future.result(timeout=_OPENAI_TIMEOUT_SECONDS)
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def _call_openai_chat_completions(self, content: List[Dict[str, Any]]):
        try:
            executor = ThreadPoolExecutor(max_workers=1)
            try:
                future = executor.submit(
                    self.openai_client.chat.completions.create,
                    model=self.openai_model,
                    messages=[{"role": "user", "content": content}],
                )
                return future.result(timeout=_OPENAI_TIMEOUT_SECONDS)
            finally:
                executor.shutdown(wait=False, cancel_futures=True)
        except Exception as e:
            logger.warning("GeminiAnalyzer: OpenAI chat fallback failed: %s", e)
            return None

    @staticmethod
    def _image_data_url(path: str) -> Optional[str]:
        try:
            with open(path, "rb") as image_file:
                encoded = base64.b64encode(image_file.read()).decode("ascii")
            return f"data:image/jpeg;base64,{encoded}"
        except Exception as e:
            logger.warning("GeminiAnalyzer: could not encode image for OpenAI fallback %s: %s", path, e)
            return None

    @staticmethod
    def _extract_openai_output_text(response: Any) -> Optional[str]:
        choices = getattr(response, "choices", None)
        if isinstance(choices, list) and choices:
            message = getattr(choices[0], "message", None)
            content = getattr(message, "content", None)
            if isinstance(content, str) and content.strip():
                return content

        output = getattr(response, "output", None)
        if not isinstance(output, list):
            return None
        chunks: List[str] = []
        for item in output:
            if isinstance(item, dict):
                content = item.get("content")
            else:
                content = getattr(item, "content", None)
            if not isinstance(content, list):
                continue
            for block in content:
                text = getattr(block, "text", None) if not isinstance(block, dict) else block.get("text")
                if text:
                    chunks.append(str(text))
        return "\n".join(chunks) if chunks else None

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
        used_selection: List[Any],
        raw_text: str,
        provider: str = "gemini",
    ) -> Dict[str, Any]:
        vehicle = parsed.get("vehicle") or {}
        ref = parsed.get("reference_image") or {}

        # Attach the actual frame path to each per-frame entry so the frontend
        # can show the image alongside Gemini's note.
        per_frame_in = parsed.get("per_frame") or []
        per_frame_out: List[Dict[str, Any]] = []
        for i, selection in enumerate(used_selection):
            if isinstance(selection, dict):
                path = selection.get("frame")
                selected_view = selection.get("view")
            else:
                path = selection
                selected_view = None
            entry = per_frame_in[i] if i < len(per_frame_in) else {}
            out = {
                "index": i + 1,
                "frame": path,
                "view": entry.get("view") or selected_view,
                "organizer_view": selected_view,
                "observations": entry.get("observations"),
                "damage_notes": entry.get("damage_notes"),
                "condition": entry.get("condition"),
            }
            if isinstance(selection, dict):
                for key in (
                    "frame_index",
                    "extracted_index",
                    "source_frame_index",
                    "timestamp_seconds",
                    "score",
                    "quality_score",
                    "vehicle_ratio",
                    "dashboard_score",
                    "clip_score",
                    "temporal_score",
                    "high_confidence",
                    "semantic_source",
                    "candidate_role",
                ):
                    if selection.get(key) is not None:
                        out[key] = selection.get(key)
            per_frame_out.append(out)
        frame_evidence_by_index = {
            entry["index"]: entry
            for entry in per_frame_out
            if entry.get("index") is not None
        }

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
            "provider": provider,
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
            "damage_items": self._normalize_damage_items(
                parsed.get("damage_items") or [],
                frame_evidence_by_index,
            ),
            "overall_condition": self._extract_overall_condition(parsed),
            "modification_findings": parsed.get("modification_findings"),
            "modification_items": self._normalize_modification_items(
                parsed.get("modification_items") or [],
                frame_evidence_by_index,
            ),
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
            "provider": None,
            "reason": reason,
            "vehicle": None,
            "per_frame": [],
            "damage_findings": None,
            "damage_items": [],
            "overall_condition": None,
            "modification_findings": None,
            "modification_items": [],
            "exhaust_observations": None,
            "odometer_observations": None,
            "reference_image": None,
            "summary": None,
        }

    @staticmethod
    def _extract_overall_condition(parsed: Dict[str, Any]) -> Any:
        if parsed.get("overall_condition") not in (None, ""):
            return parsed.get("overall_condition")
        condition = parsed.get("condition")
        if isinstance(condition, dict):
            return condition.get("overall") or condition.get("overall_condition")
        if isinstance(condition, str):
            return condition
        return None

    @staticmethod
    def _normalize_damage_items(
        items: List[Any],
        frame_evidence_by_index: Optional[Dict[int, Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        if not isinstance(items, list):
            return normalized
        allowed_types = {"scratch", "dent", "rust", "crack", "paint_damage", "missing_part", "other"}
        allowed_severity = {"low", "moderate", "high"}
        for item in items[:20]:
            if not isinstance(item, dict):
                continue
            damage_type = str(item.get("type") or "other").strip().lower()
            severity = str(item.get("severity") or "low").strip().lower()
            frame_index = _safe_int(item.get("frame_index"))
            out = {
                "type": damage_type if damage_type in allowed_types else "other",
                "location": item.get("location") or "unknown",
                "severity": severity if severity in allowed_severity else "low",
                "frame_index": frame_index,
                "confidence": _safe_float(item.get("confidence")),
                "notes": item.get("notes"),
            }
            GeminiAnalyzer._attach_frame_evidence(out, frame_evidence_by_index, frame_index)
            normalized.append(out)
        return normalized

    @staticmethod
    def _normalize_modification_items(
        items: List[Any],
        frame_evidence_by_index: Optional[Dict[int, Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        if not isinstance(items, list):
            return normalized
        allowed_parts = {"wheels", "exhaust", "lights", "body", "suspension", "paint_or_wrap", "interior", "other"}
        allowed_status = {"stock", "modified", "unknown"}
        for item in items[:20]:
            if not isinstance(item, dict):
                continue
            part = str(item.get("part") or "other").strip().lower()
            status = str(item.get("status") or "unknown").strip().lower()
            frame_index = _safe_int(item.get("frame_index"))
            out = {
                "part": part if part in allowed_parts else "other",
                "status": status if status in allowed_status else "unknown",
                "frame_index": frame_index,
                "confidence": _safe_float(item.get("confidence")),
                "notes": item.get("notes"),
            }
            GeminiAnalyzer._attach_frame_evidence(out, frame_evidence_by_index, frame_index)
            normalized.append(out)
        return normalized

    @staticmethod
    def _attach_frame_evidence(
        out: Dict[str, Any],
        frame_evidence_by_index: Optional[Dict[int, Dict[str, Any]]],
        frame_index: Optional[int],
    ) -> None:
        if not frame_evidence_by_index or frame_index is None:
            return
        evidence = frame_evidence_by_index.get(frame_index)
        if not evidence:
            return
        for source_key, output_key in (
            ("frame", "frame"),
            ("view", "view"),
            ("organizer_view", "organizer_view"),
            ("frame_index", "organizer_frame_index"),
            ("extracted_index", "extracted_index"),
            ("source_frame_index", "source_frame_index"),
            ("timestamp_seconds", "timestamp_seconds"),
            ("quality_score", "quality_score"),
            ("score", "selection_score"),
            ("high_confidence", "high_confidence"),
            ("semantic_source", "semantic_source"),
            ("candidate_role", "candidate_role"),
        ):
            if evidence.get(source_key) is not None:
                out[output_key] = evidence.get(source_key)


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _safe_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
