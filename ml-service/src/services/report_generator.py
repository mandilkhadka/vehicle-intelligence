"""
Report generation service
Generates structured inspection report using Gemini LLM
"""

import asyncio
from typing import Dict, Any
import google.generativeai as genai
import json
import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
import time

from src.config.env import load_ml_environment


class ReportGenerator:
    """Generates inspection reports using Gemini LLM"""

    def __init__(self):
        """Initialize report generator"""
        # Get API keys from service-local or repo-level environment.
        load_ml_environment()
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        
        # Validate API key format (basic check - Gemini keys typically start with AIza)
        if not api_key or len(api_key) < 20:
            print("Warning: GEMINI_API_KEY not set or invalid. Report generation will use mock data.")
            self.api_key = None
            self.model = None
        else:
            try:
                genai.configure(api_key=api_key)
                # Use gemini-2.5-pro (fast and capable)
                self.model = genai.GenerativeModel("gemini-2.5-pro")
                print("Gemini LLM initialized with gemini-2.5-pro for report generation")
                self.api_key = api_key
            except Exception as e:
                print(f"Failed to configure Gemini API: {e}")
                self.api_key = None
                self.model = None

        self.openai_client = None
        self.openai_api_key = None
        self.openai_base_url = os.getenv("OPENAI_BASE_URL", "").strip()
        self.openai_model = os.getenv("OPENAI_TEXT_MODEL", os.getenv("OPENAI_VISION_MODEL", "gpt-4.1-mini")).strip() or "gpt-4.1-mini"
        openai_key = os.getenv("OPENAI_API_KEY", "").strip()
        if (openai_key and len(openai_key) >= 20) or self.openai_base_url:
            try:
                from openai import OpenAI
                client_kwargs = {"api_key": openai_key or "local-openai-compatible"}
                if self.openai_base_url:
                    client_kwargs["base_url"] = self.openai_base_url
                self.openai_client = OpenAI(**client_kwargs)
                self.openai_api_key = client_kwargs["api_key"]
                print(f"OpenAI fallback initialized with {self.openai_model} for report generation")
            except Exception as e:
                print(f"Failed to configure OpenAI fallback: {e}")
                self.openai_client = None
                self.openai_api_key = None

    async def generate(self, inspection_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate inspection report
        Args:
            inspection_data: Dictionary with all inspection findings
        Returns:
            Structured inspection report
        """
        return await asyncio.to_thread(self._generate_sync, inspection_data)

    def _generate_sync(self, inspection_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Synchronous report generation
        """
        prompt = self._create_prompt(inspection_data)

        if self.api_key and self.model:
            report = self._generate_with_gemini(prompt, inspection_data)
            if report is not None:
                return report

        if self.openai_client and self.openai_api_key:
            report = self._generate_with_openai(prompt, inspection_data)
            if report is not None:
                return report

        return self._generate_mock_report(inspection_data)

    def _generate_with_gemini(self, prompt: str, inspection_data: Dict[str, Any]) -> Dict[str, Any] | None:
        try:
            response = self._call_gemini_with_retries(prompt)
            if response is None:
                return None
            return self._report_from_text(response.text, inspection_data)
        except Exception as e:
            print(f"Gemini report generation error: {e}")
            return None

    def _generate_with_openai(self, prompt: str, inspection_data: Dict[str, Any]) -> Dict[str, Any] | None:
        try:
            response = self._call_openai_with_retries(prompt)
            if response is None:
                return None
            report_text = getattr(response, "output_text", None) or self._extract_openai_output_text(response)
            if not report_text:
                return None
            return self._report_from_text(report_text, inspection_data)
        except Exception as e:
            print(f"OpenAI report generation error: {e}")
            return None

    def _call_gemini_with_retries(self, prompt: str):
        max_retries = 2
        timeout_seconds = 60

        for attempt in range(max_retries + 1):
            try:
                executor = ThreadPoolExecutor(max_workers=1)
                try:
                    future = executor.submit(self.model.generate_content, prompt)
                    response = future.result(timeout=timeout_seconds)
                finally:
                    executor.shutdown(wait=False, cancel_futures=True)

                if response is None:
                    print(f"Gemini API call returned no response (attempt {attempt + 1}/{max_retries + 1})")
                    if attempt < max_retries:
                        time.sleep(2 ** attempt)
                        continue
                    return None
                return response

            except FutureTimeoutError:
                print(f"Gemini API call timed out after {timeout_seconds} seconds (attempt {attempt + 1}/{max_retries + 1})")
            except Exception as e:
                error_msg = str(e)
                print(f"Gemini API call failed (attempt {attempt + 1}/{max_retries + 1}): {error_msg}")
                lower = error_msg.lower()
                if any(token in lower for token in ("429", "quota", "rate limit", "billing")):
                    return None
                if any(token in lower for token in ("403", "permission", "invalid", "api key")):
                    return None

            if attempt < max_retries:
                time.sleep(2 ** attempt)
        return None

    def _call_openai_with_retries(self, prompt: str):
        max_retries = 1
        timeout_seconds = 60

        for attempt in range(max_retries + 1):
            try:
                response = self._call_openai_responses_api(prompt, timeout_seconds)
                if response is None:
                    return None
                return response
            except FutureTimeoutError:
                print(f"OpenAI API call timed out after {timeout_seconds} seconds (attempt {attempt + 1}/{max_retries + 1})")
            except Exception as e:
                error_msg = str(e)
                print(f"OpenAI API call failed (attempt {attempt + 1}/{max_retries + 1}): {error_msg}")
                lower = error_msg.lower()
                if any(token in lower for token in ("429", "quota", "rate limit", "billing")):
                    return None
                if any(token in lower for token in ("401", "403", "permission", "invalid", "api key")):
                    return None
                chat_response = self._call_openai_chat_completions(prompt, timeout_seconds)
                if chat_response is not None:
                    return chat_response
            if attempt < max_retries:
                time.sleep(2 ** attempt)
        return None

    def _call_openai_responses_api(self, prompt: str, timeout_seconds: int):
        executor = ThreadPoolExecutor(max_workers=1)
        try:
            future = executor.submit(
                self.openai_client.responses.create,
                model=self.openai_model,
                input=[{"role": "user", "content": [{"type": "input_text", "text": prompt}]}],
            )
            return future.result(timeout=timeout_seconds)
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def _call_openai_chat_completions(self, prompt: str, timeout_seconds: int):
        try:
            executor = ThreadPoolExecutor(max_workers=1)
            try:
                future = executor.submit(
                    self.openai_client.chat.completions.create,
                    model=self.openai_model,
                    messages=[{"role": "user", "content": prompt}],
                )
                return future.result(timeout=timeout_seconds)
            finally:
                executor.shutdown(wait=False, cancel_futures=True)
        except Exception as e:
            print(f"OpenAI chat completions fallback failed: {e}")
            return None

    def _report_from_text(self, report_text: str, inspection_data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            json_start = report_text.find("{")
            json_end = report_text.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                json_str = report_text[json_start:json_end]
                return json.loads(json_str)
            return self._parse_text_report(report_text, inspection_data)
        except json.JSONDecodeError:
            return self._parse_text_report(report_text, inspection_data)

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

    def _create_prompt(self, inspection_data: Dict[str, Any]) -> str:
        """Create prompt for Gemini LLM"""
        vehicle_info = inspection_data.get("vehicle_info", {})
        odometer = inspection_data.get("odometer", {})
        damage = inspection_data.get("damage", {})
        exhaust = inspection_data.get("exhaust", {})
        local_modification = inspection_data.get("modification") or {}
        gemini_analysis = inspection_data.get("gemini_analysis") or {}
        frame_analysis = inspection_data.get("frame_analysis") or {}

        # Build detailed vehicle information
        vehicle_type = vehicle_info.get('type', 'Unknown')
        vehicle_brand = vehicle_info.get('brand', 'Unknown')
        vehicle_model = vehicle_info.get('model', 'Unknown')
        vehicle_color = vehicle_info.get('color', 'Unknown')
        vehicle_year = vehicle_info.get('year', 'Unknown')
        vehicle_variant = vehicle_info.get('variant', 'Unknown')
        vehicle_confidence = vehicle_info.get('confidence', 0)
        vehicle_category = vehicle_info.get("vehicle_category", vehicle_info.get("category", "Unknown"))
        vehicle_year_range = vehicle_info.get("year_range", "Unknown")
        vehicle_generation = vehicle_info.get("generation", "Unknown")
        vehicle_variant_candidates = json.dumps(vehicle_info.get("variant_candidates") or [])
        vehicle_variant_candidate = vehicle_info.get("variant_candidate", "Unknown")
        vehicle_variant_confidence = vehicle_info.get("variant_confidence") or 0
        vehicle_variant_candidates_ranked = json.dumps(vehicle_info.get("variant_candidates_ranked") or [])
        vehicle_model_confidence = vehicle_info.get("model_confidence") or 0
        vehicle_model_candidates = json.dumps(vehicle_info.get("model_candidates") or [])
        vehicle_identity_notes = vehicle_info.get("identity_notes")
        vehicle_identity_source = vehicle_info.get("identity_source", "video_analysis")
        vehicle_identity_override_fields = json.dumps(vehicle_info.get("identity_override_fields") or [])
        vehicle_vin = vehicle_info.get("vin")
        vehicle_registration = vehicle_info.get("registration")
        
        # Build detailed odometer information
        odometer_value = odometer.get('value')
        odometer_confidence = odometer.get('confidence', 0)
        odometer_status = self._odometer_status(odometer)
        odometer_source_frame_index = odometer.get("source_frame_index")
        odometer_timestamp_seconds = odometer.get("timestamp_seconds")
        odometer_image_path = odometer.get("speedometer_image_path") or odometer.get("crop_path")
        odometer_alternatives = json.dumps(odometer.get("alternatives") or [])
        odometer_notes = odometer.get("reasoning") or odometer.get("reason") or odometer.get("notes")
        
        # Build detailed damage information
        scratches_count = damage.get('scratches', {}).get('count', 0)
        dents_count = damage.get('dents', {}).get('count', 0)
        rust_count = damage.get('rust', {}).get('count', 0)
        cracks_count = damage.get('cracks', {}).get('count', 0)
        paint_damage_count = damage.get('paint_damage', {}).get('count', 0)
        wheel_damage_count = damage.get('wheel_damage', {}).get('count', 0)
        broken_lights_count = damage.get('broken_lights', {}).get('count', 0)
        missing_parts_count = damage.get('missing_parts', {}).get('count', 0)
        panel_misalignment_count = damage.get('panel_misalignment', {}).get('count', 0)
        damage_severity = damage.get('severity', 'low')
        
        # Build exhaust information
        exhaust_type = exhaust.get('type', 'Unknown')
        exhaust_confidence = exhaust.get('confidence', 0)

        # Gemini multimodal analysis (per-frame observations + identification)
        gemini_section = self._format_gemini_section(gemini_analysis)
        frame_section = self._format_frame_analysis_section(frame_analysis)
        modification_summary = (
            gemini_analysis.get("modification_findings")
            or local_modification.get("summary")
            or "Not assessed"
        )
        modification_items = self._combined_modification_items(
            gemini_analysis.get("modification_items") or [],
            local_modification.get("items") or [],
        )

        prompt = f"""You are an expert vehicle inspection analyst. Generate a comprehensive, accurate, and professional vehicle inspection report based on the following AI-detected findings.

The "Gemini Visual Analysis" section below contains direct observations from a multimodal vision model that examined the actual frames of the inspection video. Treat those observations as the most authoritative source — defer to them when they conflict with the other detector outputs (which use simpler computer-vision techniques). If Gemini Visual Analysis is unavailable, explicitly mark visual-only conclusions as unverified or requiring manual review.

## INSPECTION DATA:

### Vehicle Identification:
- Vehicle Type: {vehicle_type}
- Brand: {vehicle_brand}
- Model: {vehicle_model}
- Year/Generation: {vehicle_year}
- Variant: {vehicle_variant}
- Category Candidate: {vehicle_category}
- Year Range Candidate: {vehicle_year_range}
- Generation Candidate: {vehicle_generation}
- Variant Candidates: {vehicle_variant_candidates}
- Top Variant Candidate: {vehicle_variant_candidate}
- Variant Candidate Confidence: {vehicle_variant_confidence:.1%}
- Ranked Variant Candidates: {vehicle_variant_candidates_ranked}
- Model Candidate Confidence: {vehicle_model_confidence:.1%}
- Model Candidates: {vehicle_model_candidates}
- Identity Notes: {vehicle_identity_notes or 'None'}
- Identity Source: {vehicle_identity_source}
- Identity Override Fields: {vehicle_identity_override_fields}
- VIN / Chassis: {vehicle_vin or 'None'}
- Registration: {vehicle_registration or 'None'}
- Color: {vehicle_color}
- Detection Confidence: {vehicle_confidence:.1%}

{gemini_section}

{frame_section}

### Odometer Reading:
- Value: {odometer_value if odometer_value is not None else 'Not detected'} km
- Detection Confidence: {odometer_confidence:.1%}
- Status: {odometer_status}
- Source Frame Index: {odometer_source_frame_index if odometer_source_frame_index is not None else 'Unknown'}
- Timestamp Seconds: {odometer_timestamp_seconds if odometer_timestamp_seconds is not None else 'Unknown'}
- Evidence Image: {odometer_image_path or 'Unknown'}
- Alternative OCR Candidates: {odometer_alternatives}
- Reliability Notes: {odometer_notes or 'None'}

### Damage Assessment:
- Scratches Detected: {scratches_count}
- Dents Detected: {dents_count}
- Rust Areas Detected: {rust_count}
- Cracks Detected: {cracks_count}
- Paint Damage Areas Detected: {paint_damage_count}
- Wheel/Rim Damage Areas Detected: {wheel_damage_count}
- Broken Light Areas Detected: {broken_lights_count}
- Missing Trim/Parts Detected: {missing_parts_count}
- Panel Misalignment Areas Detected: {panel_misalignment_count}
- Overall Severity: {damage_severity}

### Exhaust System:
- Type: {exhaust_type}
- Detection Confidence: {exhaust_confidence:.1%}

### Modification Assessment:
- Summary: {modification_summary}
- Structured Items: {json.dumps(modification_items[:10])}

## INSTRUCTIONS:

1. **Summary**: Write a concise 2-3 sentence professional summary that highlights the key findings, overall vehicle condition, and any critical observations. Be specific about what was detected and what was not detected.

2. **Vehicle Details**: 
   - Use the exact vehicle information provided including color
   - Assess condition based on damage severity: "good" (low/no damage), "fair" (moderate damage), "poor" (significant damage)
   - If confidence is below 50%, note uncertainty in the condition assessment

3. **Odometer Reading**:
   - If value is detected: Mark as "verified" if confidence > 70%, otherwise "unverified"
   - If not detected: Mark as "unverified" and note that manual verification is required
   - Include the exact value if available

4. **Damage Assessment**:
   - Provide specific details about the type and extent of damage found
   - Use severity levels: "low" (minor cosmetic issues), "moderate" (noticeable damage), "high" (significant structural concerns)
   - Be descriptive about what was found (e.g., "3 minor scratches on passenger side", "1 dent on rear bumper", "1 broken tail light")
   - Include scratches, dents, rust, cracks, paint damage, wheel/rim damage, broken lights, missing parts, and panel misalignment when present

5. **Exhaust Status**:
   - Clearly state if exhaust is "stock" (original) or "modified" (aftermarket)
   - Add relevant notes about compliance, condition, or concerns
   - If confidence is low, note uncertainty

6. **Modification Assessment**:
   - Summarize stock-vs-modified findings across visible parts
   - Preserve structured modification items from the Gemini Visual Analysis and local CLIP modification scan when available
   - Only mark a part as "modified" when there is visible evidence; otherwise use "stock" or "unknown"

7. **Recommendations**:
   - Provide 3-5 actionable, specific recommendations
   - Prioritize safety and legal compliance
   - Include verification steps for uncertain readings
   - Suggest next steps based on findings

## OUTPUT FORMAT:

Return ONLY valid JSON in this exact structure (no markdown, no code blocks, just pure JSON):

{{
  "summary": "Professional 2-3 sentence summary of inspection findings and overall condition",
  "vehicle_details": {{
    "type": "{vehicle_type}",
    "brand": "{vehicle_brand}",
    "model": "{vehicle_model}",
    "year": "{vehicle_year}",
    "variant": "{vehicle_variant}",
    "vehicle_category": "{vehicle_category}",
    "year_range": "{vehicle_year_range}",
    "generation": "{vehicle_generation}",
    "variant_candidates": {vehicle_variant_candidates},
    "variant_candidate": "{vehicle_variant_candidate}",
    "variant_confidence": {vehicle_variant_confidence},
    "variant_candidates_ranked": {vehicle_variant_candidates_ranked},
    "model_confidence": {vehicle_model_confidence},
    "model_candidates": {vehicle_model_candidates},
    "identity_source": "{vehicle_identity_source}",
    "identity_override_fields": {vehicle_identity_override_fields},
    "vin": {json.dumps(vehicle_vin)},
    "registration": {json.dumps(vehicle_registration)},
    "color": "{vehicle_color}",
    "condition": "good|fair|poor",
    "notes": "Additional observations about vehicle condition"
  }},
  "odometer_reading": {{
    "value": {odometer_value if odometer_value is not None else 'null'},
    "status": "verified|candidate|unverified",
    "confidence": {odometer_confidence},
    "source_frame_index": {odometer_source_frame_index if odometer_source_frame_index is not None else 'null'},
    "timestamp_seconds": {odometer_timestamp_seconds if odometer_timestamp_seconds is not None else 'null'},
    "speedometer_image_path": {json.dumps(odometer_image_path)},
    "alternatives": {odometer_alternatives},
    "notes": "Specific notes about odometer reading reliability"
  }},
  "damage_assessment": {{
    "overall_severity": "low|moderate|high",
    "scratches": {scratches_count},
    "dents": {dents_count},
    "rust": {rust_count},
    "cracks": {cracks_count},
    "paint_damage": {paint_damage_count},
    "wheel_damage": {wheel_damage_count},
    "broken_lights": {broken_lights_count},
    "missing_parts": {missing_parts_count},
    "panel_misalignment": {panel_misalignment_count},
    "details": "Detailed description of all damage found, including locations and severity"
  }},
  "exhaust_status": {{
    "type": "{exhaust_type}",
    "notes": "Detailed observations about exhaust system condition and compliance"
  }},
  "modification_assessment": {{
    "summary": "Stock-vs-modified assessment across visible vehicle parts",
    "items": [
      {{
        "part": "wheels|exhaust|lights|body|suspension|paint_or_wrap|interior|other",
        "status": "stock|modified|unknown",
        "confidence": 0.0,
        "notes": "Evidence-based note"
      }}
    ]
  }},
  "recommendations": [
    "Specific recommendation 1",
    "Specific recommendation 2",
    "Specific recommendation 3"
  ]
}}

IMPORTANT: 
- Return ONLY the JSON object, no additional text before or after
- Use null (not "null" as string) for missing numeric values
- Be accurate and professional in all assessments
- Base all conclusions strictly on the provided data
"""

        return prompt

    def _format_gemini_section(self, gemini_analysis: Dict[str, Any]) -> str:
        """Render Gemini's multimodal analysis as a markdown section for the prompt."""
        if not gemini_analysis or not gemini_analysis.get("available"):
            reason = (gemini_analysis or {}).get("reason")
            suffix = f" Reason: {reason}" if reason else ""
            return f"### Gemini Visual Analysis:\n- Not available (vision pass did not run or failed).{suffix}"

        g_vehicle = gemini_analysis.get("vehicle") or {}
        per_frame = gemini_analysis.get("per_frame") or []
        ref = gemini_analysis.get("reference_image") or {}

        lines: list = []
        lines.append("### Gemini Visual Analysis:")
        lines.append(f"- Identified Vehicle: {g_vehicle.get('brand', 'Unknown')} "
                     f"{g_vehicle.get('model', '')} ({g_vehicle.get('year', 'Unknown')})")
        if g_vehicle.get("variant"):
            lines.append(f"- Variant: {g_vehicle.get('variant')}")
        lines.append(f"- Visual ID Confidence: {float(g_vehicle.get('confidence') or 0):.1%}")
        if gemini_analysis.get("overall_condition"):
            lines.append(f"- Overall Condition (visual): {gemini_analysis.get('overall_condition')}")
        if gemini_analysis.get("damage_findings"):
            lines.append(f"- Damage Findings (visual): {gemini_analysis.get('damage_findings')}")
        if gemini_analysis.get("damage_items"):
            lines.append("- Structured Visual Damage Items:")
            for item in (gemini_analysis.get("damage_items") or [])[:10]:
                lines.append(
                    f"  - {item.get('type')} at {item.get('location')} "
                    f"(severity={item.get('severity')}, confidence={float(item.get('confidence') or 0):.1%}, "
                    f"frame={item.get('frame_index')}): {item.get('notes') or 'no notes'}"
                )
        if gemini_analysis.get("modification_findings"):
            lines.append(f"- Modification Findings: {gemini_analysis.get('modification_findings')}")
        if gemini_analysis.get("modification_items"):
            lines.append("- Structured Modification Items:")
            for item in (gemini_analysis.get("modification_items") or [])[:10]:
                lines.append(
                    f"  - {item.get('part')}: {item.get('status')} "
                    f"(confidence={float(item.get('confidence') or 0):.1%}, frame={item.get('frame_index')}): "
                    f"{item.get('notes') or 'no notes'}"
                )
        if gemini_analysis.get("exhaust_observations"):
            lines.append(f"- Exhaust Observations: {gemini_analysis.get('exhaust_observations')}")
        if gemini_analysis.get("odometer_observations"):
            lines.append(f"- Odometer Observations: {gemini_analysis.get('odometer_observations')}")

        if per_frame:
            lines.append("")
            lines.append("#### Per-Frame Observations:")
            for entry in per_frame[:8]:
                idx = entry.get("index")
                view = entry.get("view") or "unspecified-view"
                obs = entry.get("observations") or "(no notes)"
                dmg = entry.get("damage_notes") or "none observed"
                cond = entry.get("condition") or "n/a"
                lines.append(f"- Frame {idx} ({view}, condition={cond}): {obs} | damage: {dmg}")

        if ref.get("description") or ref.get("search_query"):
            lines.append("")
            lines.append("#### Brand-New Reference (same model):")
            if ref.get("description"):
                lines.append(f"- Description: {ref.get('description')}")
            if ref.get("search_query"):
                lines.append(f"- Search Query: {ref.get('search_query')}")

        return "\n".join(lines)

    def _format_frame_analysis_section(self, frame_analysis: Dict[str, Any]) -> str:
        """Render organized angle/dashboard-frame metadata for report generation."""
        if not frame_analysis:
            return "### Organized Frame Analysis:\n- Not available."

        coverage = frame_analysis.get("coverage") or {}
        angle_shots = frame_analysis.get("angle_shots") or {}
        dashboard_candidates = frame_analysis.get("dashboard_candidates") or []

        lines: list = []
        lines.append("### Organized Frame Analysis:")
        lines.append(
            f"- Frames analyzed: {frame_analysis.get('frames_analyzed', 0)} "
            f"of {frame_analysis.get('frames_total', 0)}"
        )
        lines.append(f"- View coverage: {coverage.get('ratio', 0)}")
        if coverage.get("missing_views"):
            lines.append(f"- Missing views: {', '.join(coverage.get('missing_views') or [])}")
        else:
            lines.append("- Missing views: none")

        if angle_shots:
            lines.append("- Selected angle shots:")
            for view, payload in angle_shots.items():
                lines.append(
                    f"  - {view}: frame_index={payload.get('frame_index')}, "
                    f"score={payload.get('score')}, quality={payload.get('quality_score')}"
                )

        if dashboard_candidates:
            best = dashboard_candidates[0]
            lines.append(
                f"- Best dashboard/odometer candidate: frame_index={best.get('frame_index')}, "
                f"score={best.get('score')}, quality={best.get('quality_score')}"
            )

        return "\n".join(lines)

    def _parse_text_report(
        self, text: str, inspection_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Parse text report into structured format"""
        return {
            "summary": text[:500] if text else "Inspection completed",
            "vehicle_details": inspection_data.get("vehicle_info", {}),
            "odometer_reading": self._odometer_report_payload(inspection_data.get("odometer", {})),
            "damage_assessment": inspection_data.get("damage", {}),
            "exhaust_status": inspection_data.get("exhaust", {}),
            "visual_analysis": self._visual_analysis_status(inspection_data.get("gemini_analysis") or {}),
            "modification_assessment": self._fallback_modification_assessment(
                inspection_data.get("gemini_analysis") or {},
                inspection_data.get("exhaust") or {},
                inspection_data.get("modification") or {},
            ),
            "recommendations": [
                "Review vehicle condition with qualified inspector",
                "Verify odometer reading matches documentation",
            ],
        }

    def _generate_mock_report(
        self, inspection_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate mock report when API key is not available"""
        vehicle_info = inspection_data.get("vehicle_info", {})
        odometer = inspection_data.get("odometer", {})
        damage = inspection_data.get("damage", {})
        exhaust = inspection_data.get("exhaust", {})
        local_modification = inspection_data.get("modification", {})
        gemini_analysis = inspection_data.get("gemini_analysis", {})
        frame_analysis = inspection_data.get("frame_analysis", {})

        condition = self._fallback_condition(gemini_analysis, damage)

        return {
            "summary": f"Vehicle inspection completed for {vehicle_info.get('brand', 'Unknown')} {vehicle_info.get('model', 'vehicle')}. Overall condition: {condition}.",
            "vehicle_details": {
                "type": vehicle_info.get("type", "Unknown"),
                "brand": vehicle_info.get("brand", "Unknown"),
                "model": vehicle_info.get("model", "Unknown"),
                "year": vehicle_info.get("year", "Unknown"),
                "variant": vehicle_info.get("variant", "Unknown"),
                "vehicle_category": vehicle_info.get("vehicle_category", vehicle_info.get("category", "Unknown")),
                "year_range": vehicle_info.get("year_range", "Unknown"),
                "generation": vehicle_info.get("generation", "Unknown"),
                "variant_candidates": vehicle_info.get("variant_candidates") or [],
                "variant_candidate": vehicle_info.get("variant_candidate"),
                "variant_confidence": vehicle_info.get("variant_confidence"),
                "variant_candidates_ranked": vehicle_info.get("variant_candidates_ranked") or [],
                "model_confidence": vehicle_info.get("model_confidence"),
                "model_candidates": vehicle_info.get("model_candidates") or [],
                "identity_source": vehicle_info.get("identity_source"),
                "identity_override_fields": vehicle_info.get("identity_override_fields") or [],
                "vin": vehicle_info.get("vin"),
                "registration": vehicle_info.get("registration"),
                "identity_notes": vehicle_info.get("identity_notes"),
                "color": vehicle_info.get("color", "Unknown"),
                "confidence": vehicle_info.get("confidence", 0),
                "condition": condition,
            },
            "odometer_reading": self._odometer_report_payload(odometer),
            "damage_assessment": {
                "overall_severity": damage.get("severity", "low"),
                "scratches": damage.get("scratches", {}).get("count", 0),
                "dents": damage.get("dents", {}).get("count", 0),
                "rust": damage.get("rust", {}).get("count", 0),
                "cracks": damage.get("cracks", {}).get("count", 0),
                "paint_damage": damage.get("paint_damage", {}).get("count", 0),
                "wheel_damage": damage.get("wheel_damage", {}).get("count", 0),
                "broken_lights": damage.get("broken_lights", {}).get("count", 0),
                "missing_parts": damage.get("missing_parts", {}).get("count", 0),
                "panel_misalignment": damage.get("panel_misalignment", {}).get("count", 0),
                "details": (
                    f"Found {damage.get('scratches', {}).get('count', 0)} scratches, "
                    f"{damage.get('dents', {}).get('count', 0)} dents, "
                    f"{damage.get('rust', {}).get('count', 0)} rust areas, "
                    f"{damage.get('cracks', {}).get('count', 0)} cracks, "
                    f"{damage.get('paint_damage', {}).get('count', 0)} paint damage areas, "
                    f"{damage.get('wheel_damage', {}).get('count', 0)} wheel/rim damage areas, "
                    f"{damage.get('broken_lights', {}).get('count', 0)} broken light areas, "
                    f"{damage.get('missing_parts', {}).get('count', 0)} missing trim/parts, and "
                    f"{damage.get('panel_misalignment', {}).get('count', 0)} panel misalignment areas."
                ),
            },
            "exhaust_status": {
                "type": exhaust.get("type", "stock"),
                "notes": "Exhaust system appears to be in standard condition.",
            },
            "visual_analysis": self._visual_analysis_status(gemini_analysis),
            "modification_assessment": self._fallback_modification_assessment(
                gemini_analysis,
                exhaust,
                local_modification,
            ),
            "recommendations": [
                "Review vehicle condition with qualified inspector",
                "Verify odometer reading matches documentation",
                "Check exhaust system compliance if modified",
            ],
            "frame_analysis": frame_analysis,
        }

    @staticmethod
    def _fallback_condition(gemini_analysis: Dict[str, Any], damage: Dict[str, Any]) -> str:
        visual_condition = gemini_analysis.get("overall_condition")
        if isinstance(visual_condition, str) and visual_condition.strip():
            return visual_condition.strip().lower()

        damage_severity = str(damage.get("severity", "low")).strip().lower()
        if damage_severity in {"high", "severe", "poor"}:
            return "poor"
        if damage_severity in {"moderate", "medium", "fair"}:
            return "fair"
        return "good"

    @staticmethod
    def _odometer_report_payload(odometer: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "value": odometer.get("value"),
            "status": ReportGenerator._odometer_status(odometer),
            "confidence": odometer.get("confidence"),
            "source_frame_index": odometer.get("source_frame_index"),
            "timestamp_seconds": odometer.get("timestamp_seconds"),
            "speedometer_image_path": odometer.get("speedometer_image_path"),
            "source_frame_path": odometer.get("source_frame_path"),
            "organized_frame_path": odometer.get("organized_frame_path"),
            "crop_path": odometer.get("crop_path"),
            "notes": odometer.get("reasoning") or odometer.get("reason"),
            "alternatives": odometer.get("alternatives") or [],
        }

    @staticmethod
    def _odometer_status(odometer: Dict[str, Any]) -> str:
        if odometer.get("value") is None:
            return "unverified"
        confidence = float(odometer.get("confidence") or 0.0)
        return "verified" if confidence >= 0.70 else "candidate"

    @staticmethod
    def _visual_analysis_status(gemini_analysis: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "available": bool(gemini_analysis.get("available")),
            "reason": gemini_analysis.get("reason"),
        }

    def _fallback_modification_assessment(
        self,
        gemini_analysis: Dict[str, Any],
        exhaust: Dict[str, Any] | None = None,
        local_modification: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Return structured modification findings when report LLM is unavailable."""
        local_modification = local_modification or {}
        items = self._combined_modification_items(
            gemini_analysis.get("modification_items") or [],
            local_modification.get("items") or [],
        )
        if not items:
            exhaust_item = self._exhaust_modification_item(exhaust or {})
            if exhaust_item:
                items = [exhaust_item]
        summary = gemini_analysis.get("modification_findings") or local_modification.get("summary")
        if not summary:
            modified_parts = [
                item.get("part")
                for item in items
                if isinstance(item, dict) and item.get("status") == "modified"
            ]
            summary = (
                f"Potential modifications detected: {', '.join(modified_parts)}."
                if modified_parts
                else (
                    "No exhaust modification detected by the exhaust classifier; "
                    "other visual modifications require VLM/manual review."
                    if items
                    else "No visible modifications confirmed by visual analysis."
                )
            )
        return {
            "summary": summary,
            "items": items,
        }

    @staticmethod
    def _combined_modification_items(*collections) -> list:
        """Merge modification evidence without duplicating the same part/status source."""
        merged = []
        seen = set()
        for collection in collections:
            for item in collection or []:
                if not isinstance(item, dict):
                    continue
                part = str(item.get("part") or "").strip().lower()
                status = str(item.get("status") or "").strip().lower()
                source = str(item.get("source") or "").strip().lower()
                if not part:
                    continue
                key = (part, status, source)
                if key in seen:
                    continue
                seen.add(key)
                merged.append(dict(item))
        return merged

    @staticmethod
    def _exhaust_modification_item(exhaust: Dict[str, Any]) -> Dict[str, Any] | None:
        exhaust_type = str(exhaust.get("type") or "").strip().lower()
        if exhaust_type not in {"stock", "modified"}:
            return None
        return {
            "part": "exhaust",
            "status": exhaust_type,
            "confidence": exhaust.get("confidence"),
            "notes": "Derived from exhaust classifier; other modifications require VLM/manual review.",
        }
