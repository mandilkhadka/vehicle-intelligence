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

from src.services.ollama_client import OllamaClient

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


class GeminiAnalyzer:
    """Multimodal evaluation of vehicle frames with Gemini 2.5 Pro."""

    def __init__(self) -> None:
        self._genai = None
        self.model = None
        self.api_key: Optional[str] = None
        self.openai_client = None
        self.openai_api_key: Optional[str] = None
        self.openai_base_url = os.getenv("OPENAI_BASE_URL", "").strip()
        self.openai_model = os.getenv("OPENAI_VISION_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
        # Local-first VLM. When OLLAMA_BASE_URL is set, Ollama is the primary
        # provider (tried before Gemini/OpenAI); see _analyze_sync.
        self.ollama = OllamaClient.from_env()
        self._last_gemini_error: Optional[str] = None
        self._last_openai_error: Optional[str] = None
        self._last_ollama_error: Optional[str] = None
        self._last_gemini_raw: Optional[str] = None

        if self.ollama.available:
            logger.info(
                "GeminiAnalyzer: Ollama VLM enabled (primary) at %s with vision model %s",
                self.ollama.base_url,
                self.ollama.vision_model,
            )

        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key or len(api_key) < 20:
            logger.warning("GeminiAnalyzer: GEMINI_API_KEY missing/invalid — frame evaluation will be skipped")
        else:
            try:
                import google.generativeai as genai
                genai.configure(api_key=api_key)
                self._genai = genai
                # temperature=0: deterministic, less speculative damage reporting.
                self.model = genai.GenerativeModel(
                    "gemini-2.5-pro",
                    generation_config={"temperature": 0},
                )
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
        # `ollama` may be absent on instances built via __new__ in tests; treat
        # missing as "not configured" so the chain degrades to Gemini/OpenAI.
        ollama = getattr(self, "ollama", None)
        ollama_ready = bool(ollama and ollama.available)
        gemini_ready = bool(self.model and self.api_key)
        openai_ready = bool(self.openai_client and self.openai_api_key)
        if not (ollama_ready or gemini_ready or openai_ready):
            return self._unavailable_response("No Ollama, Gemini, or OpenAI VLM provider configured")

        self._last_ollama_error = None
        self._last_gemini_raw = None

        selected_with_labels = self._select_frames(frame_paths, _MAX_FRAMES_TO_SEND, frame_analysis)
        selected = [item["frame"] for item in selected_with_labels]
        if not selected:
            return self._unavailable_response("No frames available for VLM analysis")

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

        # Provider chain. Ollama is local-first (preferred); Gemini and OpenAI
        # are cloud fallbacks. Each helper returns a normalized dict on success
        # or None to fall through to the next provider.
        if ollama_ready:
            result = self._analyze_with_ollama(prompt, used_selection)
            if result is not None:
                return result

        if gemini_ready:
            result = self._analyze_with_gemini([prompt] + images, used_selection)
            if result is not None:
                return result

        if openai_ready:
            result = self._analyze_with_openai(prompt, used_selection)
            if result is not None:
                return result

        reasons = [
            getattr(self, "_last_ollama_error", None),
            self._last_gemini_error,
            self._last_openai_error,
        ]
        reason = "; ".join(str(item) for item in reasons if item)
        out = self._unavailable_response(reason or "VLM call failed after retries")
        if getattr(self, "_last_gemini_raw", None):
            out["raw_summary"] = self._last_gemini_raw[:2000]
        return out

    def _analyze_with_gemini(
        self,
        content: List[Any],
        used_selection: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        response = self._call_with_retries(content)
        if response is None:
            return None
        try:
            text = response.text or ""
        except Exception as e:
            logger.warning(f"GeminiAnalyzer: response had no text: {e}")
            self._last_gemini_error = "Gemini returned no text"
            return None
        parsed = self._parse_json_response(text)
        if parsed is None:
            self._last_gemini_error = "Gemini returned unparseable JSON"
            self._last_gemini_raw = text
            return None
        return self._normalize(parsed, used_selection, text, provider="gemini")

    def _analyze_with_ollama(
        self,
        prompt: str,
        used_selection: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        self._last_ollama_error = None
        image_paths = [item["frame"] for item in used_selection if item.get("frame")]
        text = self.ollama.chat_json(
            prompt,
            image_paths=image_paths,
            model=self.ollama.vision_model,
        )
        if not text:
            self._last_ollama_error = self.ollama.last_error or "Ollama VLM unavailable"
            return None
        parsed = self._parse_json_response(text)
        if parsed is None:
            self._last_ollama_error = "Ollama VLM unavailable: could not parse JSON"
            return None
        return self._normalize(parsed, used_selection, text, provider="ollama")

    def vlm_generate_text(self, prompt: str, image_paths: List[str]) -> Optional[str]:
        """
        Run the configured VLM (Ollama -> Gemini -> OpenAI) on a free-form
        prompt plus image files and return the raw response text. The caller
        parses the result. Used by damage_rationale so per-detection rationales
        work with whichever provider is configured. Returns None if no provider
        produced text.
        """
        image_paths = [p for p in (image_paths or []) if p]

        ollama = getattr(self, "ollama", None)
        if ollama and ollama.available:
            text = ollama.chat_json(prompt, image_paths=image_paths, model=ollama.vision_model)
            if text:
                return text

        if self.model and self.api_key and image_paths:
            images: List[Image.Image] = []
            for path in image_paths:
                try:
                    images.append(Image.open(path).convert("RGB"))
                except Exception as exc:
                    logger.debug("vlm_generate_text: unreadable image %s: %s", path, exc)
            if images:
                response = self._call_with_retries([prompt, *images])
                text = self._gemini_response_text(response)
                if text:
                    return text

        if self.openai_client and self.openai_api_key:
            selection = [{"frame": p} for p in image_paths]
            response = self._call_openai_with_retries(prompt, selection)
            if response is not None:
                text = getattr(response, "output_text", None) or self._extract_openai_output_text(response)
                if text:
                    return text

        return None

    @staticmethod
    def _gemini_response_text(response: Any) -> Optional[str]:
        """Extract text from a Gemini response, walking candidates if needed."""
        if response is None:
            return None
        try:
            text = getattr(response, "text", None)
            if text:
                return text
        except Exception:
            pass
        for cand in getattr(response, "candidates", None) or []:
            content_obj = getattr(cand, "content", None)
            for part in getattr(content_obj, "parts", None) or []:
                part_text = getattr(part, "text", None)
                if part_text:
                    return part_text
        return None

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
            "You are a meticulous, conservative automotive inspector reviewing frames "
            "from a 360° walkaround video of a single vehicle. The frames are provided "
            "in order below. Each frame is referred to by its 1-based index (1..{n}).\n\n"
            "The video-understanding preprocessor selected these representative "
            "frames and expected views:\n{labels}\n\n"
            "Carefully examine every frame and produce a STRICT JSON response in the "
            "schema below. Do not include markdown, code fences, or any text outside "
            "the JSON. Use null for unknown values. Be specific — this report will be "
            "shown to a buyer.\n\n"
            "DAMAGE POLICY — READ CAREFULLY:\n"
            "- DEFAULT ASSUMPTION: the vehicle is CLEAN and UNDAMAGED. A clean car is "
            "the normal, expected case. Most vehicles you inspect have NO damage.\n"
            "- Only report damage you can clearly SEE and justify with specific visual "
            "evidence. Do NOT invent or infer damage to appear thorough. When in "
            "doubt, report nothing and return an empty damage_items list.\n"
            "- The following are NOT damage — never report them as damage_items:\n"
            "    * reflections of sky, clouds, buildings, people, or other cars on "
            "glossy paint or glass\n"
            "    * shadows, glare, or normal lighting variation on shiny surfaces\n"
            "    * water droplets, dust, dirt, mud, pollen, or road grime\n"
            "    * panel gaps, seams, body lines, trim, and rubber molding\n"
            "    * badges, emblems, logos, antennas, sensors, cameras, door handles\n"
            "    * manufacturer/dealer stickers or tags on a new car\n"
            "- For every damage_item you DO report, the 'notes' field MUST state the "
            "exact visible defect and why it is NOT one of the non-damage items above. "
            "Omit any item you cannot justify this way.\n\n"
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
            '      "damage_notes": "any scratches, dents, rust, cracks, wheel/rim damage, broken lights, missing trim/parts, panel misalignment, paint issues — or \'none observed\'",\n'
            '      "condition": "excellent|good|fair|poor"\n'
            '    }}\n'
            '  ],\n'
            '  "damage_findings": "Aggregated 2-4 sentence description of all damage observed across frames, with locations.",\n'
            '  "damage_items": [\n'
            '    {{\n'
            '      "type": "scratch|dent|rust|crack|paint_damage|wheel_damage|broken_light|missing_part|panel_misalignment|other",\n'
            '      "location": "specific vehicle area, e.g. front bumper, left door, rear fender",\n'
            '      "severity": "low|moderate|high",\n'
            '      "frame_index": 1,\n'
            '      "region": [ymin, xmin, ymax, xmax],\n'
            '      "confidence": 0.0-1.0,\n'
            '      "notes": "REQUIRED: exact visible defect and why it is not a reflection/shadow/dirt/trim/badge"\n'
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
            "- For damage_notes and damage_items, do NOT invent damage that is not clearly visible; per the DAMAGE POLICY above, return an empty list when the vehicle looks clean.\n"
            "- damage_items.region is the bounding box of the damage in the SAME frame given by frame_index, as integers [ymin, xmin, ymax, xmax] normalized to a 0-1000 grid (top-left origin). Use null if you cannot localize it.\n"
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
                temperature=0,
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
                    temperature=0,
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
        """
        Normalize and GATE the VLM's raw damage items. The VLM is the
        authoritative damage source, so we do not trust it to self-suppress:

        1. confidence floor (ML_DAMAGE_VLM_MIN_CONFIDENCE, default 0.55)
        2. evidence required — drop items with empty `notes`
        3. multi-frame consensus — cluster by (type, location); a cluster only
           survives if seen in >= ML_DAMAGE_CONSENSUS_MIN_FRAMES distinct frames
           (default 2; a reflection/shadow appears in one frame, real damage from
           several walkaround angles). A single-frame item still survives if its
           confidence >= ML_DAMAGE_VLM_HIGH_CONFIDENCE (default 0.85) so obvious
           damage in one good shot is never dropped. Set CONSENSUS_MIN_FRAMES=1
           to disable the multi-frame requirement.

        Each surviving cluster is collapsed to its highest-confidence
        representative, so the same physical damage seen from multiple angles
        becomes one finding.
        """
        if not isinstance(items, list):
            return []

        allowed_types = {
            "scratch",
            "dent",
            "rust",
            "crack",
            "paint_damage",
            "wheel_damage",
            "broken_light",
            "missing_part",
            "panel_misalignment",
            "other",
        }
        allowed_severity = {"low", "moderate", "high"}

        min_confidence = _env_float("ML_DAMAGE_VLM_MIN_CONFIDENCE", 0.55)
        high_confidence = _env_float("ML_DAMAGE_VLM_HIGH_CONFIDENCE", 0.85)
        consensus_min_frames = max(1, _env_int("ML_DAMAGE_CONSENSUS_MIN_FRAMES", 2))

        # Stage 1+2: per-item normalization, confidence floor, evidence required.
        candidates: List[Dict[str, Any]] = []
        for item in items[:40]:
            if not isinstance(item, dict):
                continue
            confidence = _safe_float(item.get("confidence"))
            if confidence < min_confidence:
                continue
            notes = item.get("notes")
            if not (isinstance(notes, str) and notes.strip()):
                continue  # evidence required

            damage_type = str(item.get("type") or "other").strip().lower()
            severity = str(item.get("severity") or "low").strip().lower()
            frame_index = _safe_int(item.get("frame_index"))
            out: Dict[str, Any] = {
                "type": damage_type if damage_type in allowed_types else "other",
                "location": item.get("location") or "unknown",
                "severity": severity if severity in allowed_severity else "low",
                "frame_index": frame_index,
                "confidence": confidence,
                "notes": notes,
            }
            region = GeminiAnalyzer._normalize_region(item.get("region"))
            if region is not None:
                out["region"] = region
            GeminiAnalyzer._attach_frame_evidence(out, frame_evidence_by_index, frame_index)
            candidates.append(out)

        # Stage 3: cluster by (type, normalized location) and apply consensus.
        clusters: Dict[tuple, List[Dict[str, Any]]] = {}
        for cand in candidates:
            key = (cand["type"], str(cand["location"]).strip().lower())
            clusters.setdefault(key, []).append(cand)

        normalized: List[Dict[str, Any]] = []
        for group in clusters.values():
            best = max(group, key=lambda c: c.get("confidence", 0.0))
            distinct_frames = {
                c["frame_index"] for c in group if c.get("frame_index") is not None
            }
            if len(distinct_frames) >= consensus_min_frames or best["confidence"] >= high_confidence:
                normalized.append(best)

        normalized.sort(key=lambda c: c.get("confidence", 0.0), reverse=True)
        return normalized

    @staticmethod
    def _normalize_region(region: Any) -> Optional[List[float]]:
        """Validate a VLM region as 4 finite numbers [ymin, xmin, ymax, xmax]."""
        if not isinstance(region, (list, tuple)) or len(region) != 4:
            return None
        out: List[float] = []
        for value in region:
            try:
                out.append(float(value))
            except (TypeError, ValueError):
                return None
        return out

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
