from src.services.report_generator import ReportGenerator


def test_report_generator_accepts_openai_compatible_base_url_without_public_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:11434/v1")

    generator = ReportGenerator()

    assert generator.openai_client is not None
    assert generator.openai_api_key == "local-openai-compatible"
    assert generator.openai_base_url == "http://localhost:11434/v1"


class FakeFailingReportModel:
    def generate_content(self, prompt):
        raise RuntimeError("429 billing cap exceeded")


class FakeOpenAIReportResponses:
    def __init__(self, text):
        self.text = text
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return type("OpenAIResponse", (), {"output_text": self.text})()


class FakeOpenAIReportClient:
    def __init__(self, text):
        self.responses = FakeOpenAIReportResponses(text)


class FakeFailingOpenAIReportResponses:
    def create(self, **kwargs):
        raise RuntimeError("responses endpoint not supported")


class FakeOpenAIReportChatCompletions:
    def __init__(self, text):
        self.text = text
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        message = type("Message", (), {"content": self.text})()
        choice = type("Choice", (), {"message": message})()
        return type("ChatResponse", (), {"choices": [choice]})()


class FakeOpenAIReportChat:
    def __init__(self, text):
        self.completions = FakeOpenAIReportChatCompletions(text)


class FakeOpenAIReportChatOnlyClient:
    def __init__(self, text):
        self.responses = FakeFailingOpenAIReportResponses()
        self.chat = FakeOpenAIReportChat(text)


def test_report_generator_uses_openai_fallback_when_gemini_quota_fails():
    generator = ReportGenerator.__new__(ReportGenerator)
    generator.api_key = "configured-gemini-key"
    generator.model = FakeFailingReportModel()
    generator.openai_api_key = "configured-openai-key"
    generator.openai_model = "gpt-4.1-mini"
    generator.openai_client = FakeOpenAIReportClient(
        """
        {
          "summary": "OpenAI generated inspection summary.",
          "vehicle_details": {
            "type": "car",
            "brand": "Toyota",
            "model": "Sienta",
            "year": "2024",
            "variant": "X",
            "condition": "good"
          },
          "odometer_reading": {"value": 12292, "status": "verified"},
          "damage_assessment": {"overall_severity": "low", "details": "No major damage."},
          "exhaust_status": {"type": "stock", "notes": "Factory exhaust."},
          "recommendations": ["Run a final manual identity check."]
        }
        """
    )

    report = generator._generate_sync(
        {
            "vehicle_info": {"brand": "Toyota", "model": "Sienta", "type": "car"},
            "odometer": {"value": 12292, "confidence": 0.76},
            "damage": {"severity": "low"},
            "exhaust": {"type": "stock"},
            "gemini_analysis": {},
        }
    )

    assert report["summary"] == "OpenAI generated inspection summary."
    assert report["vehicle_details"]["variant"] == "X"
    assert generator.openai_client.responses.calls


def test_report_generator_uses_openai_chat_fallback_for_compatible_local_servers():
    generator = ReportGenerator.__new__(ReportGenerator)
    generator.api_key = "configured-gemini-key"
    generator.model = FakeFailingReportModel()
    generator.openai_api_key = "local-openai-compatible"
    generator.openai_model = "local-vlm"
    generator.openai_client = FakeOpenAIReportChatOnlyClient(
        """
        {
          "summary": "Local VLM generated inspection summary.",
          "vehicle_details": {
            "type": "car",
            "brand": "Toyota",
            "model": "Sienta",
            "year": "2024",
            "variant": "X"
          },
          "recommendations": []
        }
        """
    )

    report = generator._generate_sync(
        {
            "vehicle_info": {"brand": "Toyota", "model": "Sienta", "type": "car"},
            "odometer": {},
            "damage": {},
            "exhaust": {},
            "gemini_analysis": {},
        }
    )

    assert report["summary"] == "Local VLM generated inspection summary."
    assert report["vehicle_details"]["variant"] == "X"
    assert generator.openai_client.chat.completions.calls


def test_mock_report_includes_modification_assessment_from_gemini():
    generator = ReportGenerator()
    report = generator._generate_mock_report(
        {
            "vehicle_info": {"brand": "Toyota", "model": "Camry", "type": "car"},
            "odometer": {
                "value": 12345,
                "confidence": 0.91,
                "source_frame_index": 210,
                "timestamp_seconds": 3.5,
                "speedometer_image_path": "frames/odometer_crop.jpg",
                "alternatives": [{"value": 12340, "confidence": 0.42}],
            },
            "damage": {"severity": "low"},
            "exhaust": {"type": "stock"},
            "gemini_analysis": {
                "modification_findings": "Wheels appear aftermarket.",
                "modification_items": [
                    {
                        "part": "wheels",
                        "status": "modified",
                        "confidence": 0.76,
                        "notes": "Non-factory wheel design.",
                    }
                ],
            },
        }
    )

    assert report["modification_assessment"]["summary"] == "Wheels appear aftermarket."
    assert report["modification_assessment"]["items"][0]["part"] == "wheels"
    assert report["modification_assessment"]["items"][0]["status"] == "modified"
    assert report["odometer_reading"]["confidence"] == 0.91
    assert report["odometer_reading"]["source_frame_index"] == 210
    assert report["odometer_reading"]["timestamp_seconds"] == 3.5
    assert report["odometer_reading"]["speedometer_image_path"] == "frames/odometer_crop.jpg"
    assert report["odometer_reading"]["status"] == "verified"
    assert report["odometer_reading"]["alternatives"][0]["value"] == 12340


def test_mock_report_prefers_gemini_condition_and_preserves_vehicle_details():
    generator = ReportGenerator()
    report = generator._generate_mock_report(
        {
            "vehicle_info": {
                "brand": "Toyota",
                "model": "Camry",
                "type": "car",
                "year": "2024",
                "variant": "Hybrid XLE",
                "color": "white",
                "confidence": 0.93,
            },
            "odometer": {"value": 12345},
            "damage": {"severity": "high"},
            "exhaust": {"type": "stock"},
            "gemini_analysis": {
                "overall_condition": "good",
            },
        }
    )

    assert report["vehicle_details"]["condition"] == "good"
    assert report["vehicle_details"]["year"] == "2024"
    assert report["vehicle_details"]["variant"] == "Hybrid XLE"
    assert report["vehicle_details"]["confidence"] == 0.93


def test_mock_report_preserves_local_identity_candidates():
    generator = ReportGenerator()
    report = generator._generate_mock_report(
        {
            "vehicle_info": {
                "brand": "Toyota",
                "model": "Sienta",
                "type": "car",
                "vehicle_category": "compact minivan",
                "year_range": "2022-present",
                "generation": "third generation",
                "variant_candidates": ["Hybrid", "Z", "G", "X"],
                "variant_candidate": "Hybrid",
                "variant_confidence": 0.72,
                "variant_candidates_ranked": [
                    {"variant": "Hybrid", "confidence": 0.72},
                    {"variant": "Z", "confidence": 0.21},
                ],
                "model_confidence": 0.9933,
                "model_candidates": [{"model": "Sienta", "confidence": 0.9933}],
                "identity_notes": "Exact year and trim require manual verification.",
            },
            "odometer": {},
            "damage": {"severity": "low"},
            "exhaust": {"type": "stock"},
            "gemini_analysis": {},
        }
    )

    details = report["vehicle_details"]
    assert details["vehicle_category"] == "compact minivan"
    assert details["year_range"] == "2022-present"
    assert details["generation"] == "third generation"
    assert details["variant_candidates"] == ["Hybrid", "Z", "G", "X"]
    assert details["variant_candidate"] == "Hybrid"
    assert details["variant_confidence"] == 0.72
    assert details["variant_candidates_ranked"][0]["variant"] == "Hybrid"
    assert details["model_candidates"][0]["model"] == "Sienta"
    assert "manual verification" in details["identity_notes"]


def test_mock_report_uses_exhaust_classifier_for_fallback_modification_item():
    generator = ReportGenerator()
    report = generator._generate_mock_report(
        {
            "vehicle_info": {"brand": "Toyota", "model": "Camry", "type": "car"},
            "odometer": {},
            "damage": {"severity": "low"},
            "exhaust": {"type": "stock", "confidence": 0.7},
            "gemini_analysis": {
                "available": False,
                "reason": "Gemini API unavailable: quota exceeded",
            },
        }
    )

    item = report["modification_assessment"]["items"][0]
    assert item["part"] == "exhaust"
    assert item["status"] == "stock"
    assert item["confidence"] == 0.7
    assert "exhaust classifier" in item["notes"]
    assert "other visual modifications require VLM/manual review" in report["modification_assessment"]["summary"]


def test_mock_report_uses_local_modification_analysis_items():
    generator = ReportGenerator()
    report = generator._generate_mock_report(
        {
            "vehicle_info": {"brand": "Toyota", "model": "Camry", "type": "car"},
            "odometer": {},
            "damage": {"severity": "low"},
            "exhaust": {"type": "stock", "confidence": 0.7},
            "modification": {
                "summary": "Local CLIP modification scan produced concrete evidence.",
                "items": [
                    {
                        "part": "wheels",
                        "status": "stock",
                        "confidence": 0.74,
                        "source": "local_clip",
                    },
                    {
                        "part": "lights",
                        "status": "stock",
                        "confidence": 0.72,
                        "source": "local_clip",
                    },
                ],
            },
            "gemini_analysis": {
                "available": False,
                "reason": "Gemini API unavailable: quota exceeded",
            },
        }
    )

    modification = report["modification_assessment"]
    assert modification["summary"] == "Local CLIP modification scan produced concrete evidence."
    assert [item["part"] for item in modification["items"]] == ["wheels", "lights"]
    assert modification["items"][0]["source"] == "local_clip"


def test_mock_report_maps_damage_severity_to_condition_when_gemini_missing():
    generator = ReportGenerator()

    assert generator._fallback_condition({}, {"severity": "low"}) == "good"
    assert generator._fallback_condition({}, {"severity": "medium"}) == "fair"
    assert generator._fallback_condition({}, {"severity": "high"}) == "poor"


def test_report_prompt_includes_odometer_evidence_metadata():
    generator = ReportGenerator()
    prompt = generator._create_prompt(
        {
            "vehicle_info": {"brand": "Toyota", "model": "Camry", "type": "car"},
            "odometer": {
                "value": 45230,
                "confidence": 0.42,
                "source_frame_index": 630,
                "timestamp_seconds": 10.52,
                "speedometer_image_path": "frames/inspection/organized/odometer_crop.jpg",
                "reason": "Local OCR produced only low-confidence or conflicting odometer candidates; manual/VLM verification is required",
                "alternatives": [{"value": 9230, "confidence": 0.42, "occurrences": 1}],
            },
            "damage": {"severity": "low"},
            "exhaust": {"type": "stock"},
            "gemini_analysis": {},
            "frame_analysis": {},
        }
    )

    assert "Source Frame Index: 630" in prompt
    assert "Timestamp Seconds: 10.52" in prompt
    assert "Alternative OCR Candidates" in prompt
    assert "Reliability Notes: Local OCR produced only low-confidence" in prompt
    assert '"value": 9230' in prompt
    assert '"source_frame_index": 630' in prompt
    assert '"timestamp_seconds": 10.52' in prompt
    assert '"status": "verified|candidate|unverified"' in prompt


def test_report_prompt_includes_identity_candidate_metadata():
    generator = ReportGenerator()
    prompt = generator._create_prompt(
        {
            "vehicle_info": {
                "brand": "Toyota",
                "model": "Sienta",
                "type": "car",
                "vehicle_category": "compact minivan",
                "year_range": "2022-present",
                "generation": "third generation",
                "variant_candidates": ["Hybrid", "Z"],
                "variant_candidate": "Hybrid",
                "variant_confidence": 0.72,
                "variant_candidates_ranked": [
                    {"variant": "Hybrid", "confidence": 0.72},
                    {"variant": "Z", "confidence": 0.21},
                ],
                "model_confidence": 0.9933,
                "model_candidates": [{"model": "Sienta", "confidence": 0.9933}],
                "identity_notes": "Exact year and trim require VLM/manual verification.",
            },
            "odometer": {},
            "damage": {"severity": "low"},
            "exhaust": {"type": "stock"},
            "gemini_analysis": {},
            "frame_analysis": {},
        }
    )

    assert "Category Candidate: compact minivan" in prompt
    assert "Year Range Candidate: 2022-present" in prompt
    assert "Generation Candidate: third generation" in prompt
    assert "Variant Candidates: [\"Hybrid\", \"Z\"]" in prompt
    assert "Top Variant Candidate: Hybrid" in prompt
    assert "Variant Candidate Confidence: 72.0%" in prompt
    assert "Ranked Variant Candidates: [{\"variant\": \"Hybrid\", \"confidence\": 0.72}" in prompt
    assert "Exact year and trim require VLM/manual verification" in prompt


def test_report_marks_unavailable_visual_analysis():
    generator = ReportGenerator()
    report = generator._generate_mock_report(
        {
            "vehicle_info": {"brand": "Toyota", "model": "Camry", "type": "car"},
            "odometer": {},
            "damage": {"severity": "low"},
            "exhaust": {"type": "stock"},
            "gemini_analysis": {
                "available": False,
                "reason": "Gemini API unavailable: quota, rate limit, or billing cap exceeded",
            },
        }
    )
    prompt = generator._create_prompt(
        {
            "vehicle_info": {"brand": "Toyota", "model": "Camry", "type": "car"},
            "odometer": {},
            "damage": {"severity": "low"},
            "exhaust": {"type": "stock"},
            "gemini_analysis": report["visual_analysis"],
            "frame_analysis": {},
        }
    )

    assert report["visual_analysis"]["available"] is False
    assert "billing cap" in report["visual_analysis"]["reason"]
    assert "Not available" in prompt
    assert "billing cap" in prompt
