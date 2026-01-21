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
        # Try loading from .env file if not set
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        
        # Validate API key format (basic check - Gemini keys typically start with AIza)
        if not api_key or len(api_key) < 20:
            print("Warning: GEMINI_API_KEY not set or invalid. Report generation will use mock data.")
            self.api_key = None
            self.model = None
        else:
            try:
                genai.configure(api_key=api_key)
                # Try gemini-1.5-flash first (faster, more stable), fallback to gemini-1.5-pro
                try:
                    self.model = genai.GenerativeModel("gemini-1.5-flash")
                    print("Gemini LLM initialized with gemini-1.5-flash for report generation")
                except Exception as e:
                    print(f"Failed to initialize gemini-1.5-flash, trying gemini-1.5-pro: {e}")
                    try:
                        self.model = genai.GenerativeModel("gemini-1.5-pro")
                        print("Gemini LLM initialized with gemini-1.5-pro for report generation")
                    except Exception as e2:
                        print(f"Failed to initialize gemini-1.5-pro, trying legacy gemini-pro: {e2}")
                        self.model = genai.GenerativeModel("gemini-pro")
                        print("Gemini LLM initialized with legacy gemini-pro for report generation")
                self.api_key = api_key
            except Exception as e:
                print(f"Failed to configure Gemini API: {e}")
                self.api_key = None
                self.model = None

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
        # If no API key or model, return a structured mock report
        if not self.api_key or not self.model:
            return self._generate_mock_report(inspection_data)

        try:
            # Prepare prompt for Gemini
            prompt = self._create_prompt(inspection_data)

            # Generate report using Gemini with timeout and retry logic (60 seconds timeout, 2 retries)
            from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
            import time
            
            max_retries = 2
            timeout_seconds = 60
            
            response = None
            for attempt in range(max_retries + 1):
                try:
                    with ThreadPoolExecutor(max_workers=1) as executor:
                        future = executor.submit(self.model.generate_content, prompt)
                        response = future.result(timeout=timeout_seconds)
                    
                    if response is None:
                        print(f"Gemini API call returned no response (attempt {attempt + 1}/{max_retries + 1})")
                        if attempt < max_retries:
                            time.sleep(2 ** attempt)  # Exponential backoff: 1s, 2s
                            continue
                        # Fallback to mock report instead of raising
                        print("Falling back to mock report after all retries failed")
                        return self._generate_mock_report(inspection_data)
                    
                    # Success - break out of retry loop
                    break
                    
                except FutureTimeoutError:
                    print(f"Gemini API call timed out after {timeout_seconds} seconds (attempt {attempt + 1}/{max_retries + 1})")
                    if attempt < max_retries:
                        time.sleep(2 ** attempt)  # Exponential backoff
                        continue
                    # Fallback to mock report instead of raising
                    print("Falling back to mock report after timeout")
                    return self._generate_mock_report(inspection_data)
                    
                except Exception as e:
                    error_msg = str(e)
                    print(f"Gemini API call failed (attempt {attempt + 1}/{max_retries + 1}): {error_msg}")
                    
                    # Check for specific error types that shouldn't be retried
                    if "429" in error_msg or "quota" in error_msg.lower() or "rate limit" in error_msg.lower():
                        print("Rate limit exceeded, falling back to mock report")
                        return self._generate_mock_report(inspection_data)
                    if "403" in error_msg or "permission" in error_msg.lower() or "invalid" in error_msg.lower():
                        print("Authentication/permission error, falling back to mock report")
                        return self._generate_mock_report(inspection_data)
                    
                    if attempt < max_retries:
                        time.sleep(2 ** attempt)  # Exponential backoff
                        continue
                    # Fallback to mock report instead of raising
                    print("Falling back to mock report after all retries failed")
                    return self._generate_mock_report(inspection_data)
            
            if response is None:
                print("Gemini API call returned no response after all retries")
                return self._generate_mock_report(inspection_data)

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

        # Build detailed vehicle information
        vehicle_type = vehicle_info.get('type', 'Unknown')
        vehicle_brand = vehicle_info.get('brand', 'Unknown')
        vehicle_model = vehicle_info.get('model', 'Unknown')
        vehicle_color = vehicle_info.get('color', 'Unknown')
        vehicle_confidence = vehicle_info.get('confidence', 0)
        
        # Build detailed odometer information
        odometer_value = odometer.get('value')
        odometer_confidence = odometer.get('confidence', 0)
        odometer_status = "detected" if odometer_value is not None else "not detected"
        
        # Build detailed damage information
        scratches_count = damage.get('scratches', {}).get('count', 0)
        dents_count = damage.get('dents', {}).get('count', 0)
        rust_count = damage.get('rust', {}).get('count', 0)
        damage_severity = damage.get('severity', 'low')
        
        # Build exhaust information
        exhaust_type = exhaust.get('type', 'Unknown')
        exhaust_confidence = exhaust.get('confidence', 0)

        prompt = f"""You are an expert vehicle inspection analyst. Generate a comprehensive, accurate, and professional vehicle inspection report based on the following AI-detected findings.

## INSPECTION DATA:

### Vehicle Identification:
- Vehicle Type: {vehicle_type}
- Brand: {vehicle_brand}
- Model: {vehicle_model}
- Color: {vehicle_color}
- Detection Confidence: {vehicle_confidence:.1%}

### Odometer Reading:
- Value: {odometer_value if odometer_value is not None else 'Not detected'} km
- Detection Confidence: {odometer_confidence:.1%}
- Status: {odometer_status}

### Damage Assessment:
- Scratches Detected: {scratches_count}
- Dents Detected: {dents_count}
- Rust Areas Detected: {rust_count}
- Overall Severity: {damage_severity}

### Exhaust System:
- Type: {exhaust_type}
- Detection Confidence: {exhaust_confidence:.1%}

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
   - Be descriptive about what was found (e.g., "3 minor scratches on passenger side", "1 dent on rear bumper")

5. **Exhaust Status**:
   - Clearly state if exhaust is "stock" (original) or "modified" (aftermarket)
   - Add relevant notes about compliance, condition, or concerns
   - If confidence is low, note uncertainty

6. **Recommendations**:
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
    "color": "{vehicle_color}",
    "condition": "good|fair|poor",
    "notes": "Additional observations about vehicle condition"
  }},
  "odometer_reading": {{
    "value": {odometer_value if odometer_value is not None else 'null'},
    "status": "verified|unverified",
    "notes": "Specific notes about odometer reading reliability"
  }},
  "damage_assessment": {{
    "overall_severity": "low|moderate|high",
    "scratches": {scratches_count},
    "dents": {dents_count},
    "rust": {rust_count},
    "details": "Detailed description of all damage found, including locations and severity"
  }},
  "exhaust_status": {{
    "type": "{exhaust_type}",
    "notes": "Detailed observations about exhaust system condition and compliance"
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
                "color": vehicle_info.get("color", "Unknown"),
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
