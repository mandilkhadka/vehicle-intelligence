"""
Report generation service
Generates structured inspection report using Gemini LLM
"""

import asyncio
from typing import Dict, Any
import google.generativeai as genai
import json
import os


class ReportGenerator:
    """Generates inspection reports using Gemini LLM"""

    def __init__(self):
        """Initialize report generator"""
        # Get API key from environment variable
        api_key = os.getenv("GEMINI_API_KEY", "")
        
        if not api_key:
            print("Warning: GEMINI_API_KEY not set. Report generation will use mock data.")
            self.api_key = None
        else:
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel("gemini-pro")
            self.api_key = api_key

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
        # If no API key, return a structured mock report
        if not self.api_key:
            return self._generate_mock_report(inspection_data)

        try:
            # Prepare prompt for Gemini
            prompt = self._create_prompt(inspection_data)

            # Generate report using Gemini
            response = self.model.generate_content(prompt)

            # Parse response
            report_text = response.text

            # Try to extract JSON from response
            try:
                # Look for JSON in the response
                json_start = report_text.find("{")
                json_end = report_text.rfind("}") + 1
                if json_start >= 0 and json_end > json_start:
                    json_str = report_text[json_start:json_end]
                    report = json.loads(json_str)
                else:
                    # If no JSON found, create structured report from text
                    report = self._parse_text_report(report_text, inspection_data)
            except json.JSONDecodeError:
                # If JSON parsing fails, create structured report from text
                report = self._parse_text_report(report_text, inspection_data)

            return report

        except Exception as e:
            print(f"Report generation error: {e}")
            # Fallback to mock report
            return self._generate_mock_report(inspection_data)

    def _create_prompt(self, inspection_data: Dict[str, Any]) -> str:
        """Create prompt for Gemini LLM"""
        vehicle_info = inspection_data.get("vehicle_info", {})
        odometer = inspection_data.get("odometer", {})
        damage = inspection_data.get("damage", {})
        exhaust = inspection_data.get("exhaust", {})

        prompt = f"""
Generate a comprehensive vehicle inspection report in JSON format based on the following findings:

Vehicle Information:
- Type: {vehicle_info.get('type', 'Unknown')}
- Brand: {vehicle_info.get('brand', 'Unknown')}
- Model: {vehicle_info.get('model', 'Unknown')}
- Confidence: {vehicle_info.get('confidence', 0)}

Odometer Reading:
- Value: {odometer.get('value', 'Not detected')} km
- Confidence: {odometer.get('confidence', 0)}

Damage Assessment:
- Scratches: {damage.get('scratches', {}).get('count', 0)} detected
- Dents: {damage.get('dents', {}).get('count', 0)} detected
- Rust: {damage.get('rust', {}).get('count', 0)} detected
- Severity: {damage.get('severity', 'Unknown')}

Exhaust System:
- Type: {exhaust.get('type', 'Unknown')}
- Confidence: {exhaust.get('confidence', 0)}

Please generate a structured JSON report with the following format:
{{
  "summary": "Brief overall assessment",
  "vehicle_details": {{
    "type": "...",
    "brand": "...",
    "model": "...",
    "condition": "good/fair/poor"
  }},
  "odometer_reading": {{
    "value": ...,
    "status": "verified/unverified"
  }},
  "damage_assessment": {{
    "overall_severity": "low/high",
    "details": "Description of damage found"
  }},
  "exhaust_status": {{
    "type": "stock/modified",
    "notes": "Additional observations"
  }},
  "recommendations": ["Recommendation 1", "Recommendation 2"]
}}
"""

        return prompt

    def _parse_text_report(
        self, text: str, inspection_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Parse text report into structured format"""
        return {
            "summary": text[:500] if text else "Inspection completed",
            "vehicle_details": inspection_data.get("vehicle_info", {}),
            "odometer_reading": inspection_data.get("odometer", {}),
            "damage_assessment": inspection_data.get("damage", {}),
            "exhaust_status": inspection_data.get("exhaust", {}),
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

        # Determine overall condition
        damage_severity = damage.get("severity", "low")
        condition = "good" if damage_severity == "low" else "fair"

        return {
            "summary": f"Vehicle inspection completed for {vehicle_info.get('brand', 'Unknown')} {vehicle_info.get('model', 'vehicle')}. Overall condition: {condition}.",
            "vehicle_details": {
                "type": vehicle_info.get("type", "Unknown"),
                "brand": vehicle_info.get("brand", "Unknown"),
                "model": vehicle_info.get("model", "Unknown"),
                "condition": condition,
            },
            "odometer_reading": {
                "value": odometer.get("value"),
                "status": "verified" if odometer.get("value") else "unverified",
            },
            "damage_assessment": {
                "overall_severity": damage.get("severity", "low"),
                "details": f"Found {damage.get('scratches', {}).get('count', 0)} scratches, {damage.get('dents', {}).get('count', 0)} dents, and {damage.get('rust', {}).get('count', 0)} rust areas.",
            },
            "exhaust_status": {
                "type": exhaust.get("type", "stock"),
                "notes": "Exhaust system appears to be in standard condition.",
            },
            "recommendations": [
                "Review vehicle condition with qualified inspector",
                "Verify odometer reading matches documentation",
                "Check exhaust system compliance if modified",
            ],
        }
