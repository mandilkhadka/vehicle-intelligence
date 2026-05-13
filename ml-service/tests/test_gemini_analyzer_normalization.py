import cv2
import numpy as np

from src.services.gemini_analyzer import GeminiAnalyzer


def test_analyzer_accepts_openai_compatible_base_url_without_public_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:11434/v1")

    analyzer = GeminiAnalyzer()

    assert analyzer.openai_client is not None
    assert analyzer.openai_api_key == "local-openai-compatible"
    assert analyzer.openai_base_url == "http://localhost:11434/v1"


def test_normalize_includes_structured_damage_and_modifications():
    analyzer = GeminiAnalyzer()

    result = analyzer._normalize(
        {
            "vehicle": {
                "type": "car",
                "brand": "Toyota",
                "model": "Camry",
                "confidence": 0.91,
            },
            "per_frame": [{"view": "front", "observations": "front visible"}],
            "damage_items": [
                {
                    "type": "paint_damage",
                    "location": "front bumper",
                    "severity": "moderate",
                    "frame_index": "1",
                    "confidence": "0.82",
                    "notes": "scuffing visible",
                }
            ],
            "modification_items": [
                {
                    "part": "wheels",
                    "status": "modified",
                    "frame_index": 1,
                    "confidence": 0.76,
                    "notes": "aftermarket wheel design",
                }
            ],
            "modification_findings": "Wheels appear aftermarket.",
            "condition": {"overall": "Good"},
            "reference_image": {"search_query": "Toyota Camry official press image"},
        },
        [
            {
                "frame": "frame_0001.jpg",
                "view": "front",
                "frame_index": 3,
                "extracted_index": 7,
                "source_frame_index": 210,
                "timestamp_seconds": 3.5,
                "quality_score": 0.93,
                "score": 0.88,
                "high_confidence": True,
                "semantic_source": "clip",
            }
        ],
        "{}",
    )

    assert result["damage_items"] == [
        {
            "type": "paint_damage",
            "location": "front bumper",
            "severity": "moderate",
            "frame_index": 1,
            "confidence": 0.82,
            "notes": "scuffing visible",
            "frame": "frame_0001.jpg",
            "view": "front",
            "organizer_view": "front",
            "organizer_frame_index": 3,
            "extracted_index": 7,
            "source_frame_index": 210,
            "timestamp_seconds": 3.5,
            "quality_score": 0.93,
            "selection_score": 0.88,
            "high_confidence": True,
            "semantic_source": "clip",
        }
    ]
    assert result["modification_items"][0]["part"] == "wheels"
    assert result["modification_items"][0]["status"] == "modified"
    assert result["modification_items"][0]["frame"] == "frame_0001.jpg"
    assert result["modification_items"][0]["source_frame_index"] == 210
    assert result["modification_findings"] == "Wheels appear aftermarket."
    assert result["overall_condition"] == "Good"
    assert result["per_frame"][0]["organizer_view"] == "front"
    assert result["per_frame"][0]["extracted_index"] == 7
    assert result["per_frame"][0]["source_frame_index"] == 210
    assert result["per_frame"][0]["timestamp_seconds"] == 3.5
    assert result["per_frame"][0]["quality_score"] == 0.93
    assert result["per_frame"][0]["score"] == 0.88
    assert result["per_frame"][0]["high_confidence"] is True
    assert result["per_frame"][0]["semantic_source"] == "clip"


class FakeFailingGeminiModel:
    def __init__(self, error):
        self.error = error
        self.calls = []

    def generate_content(self, content):
        self.calls.append(content)
        raise RuntimeError(self.error)


def test_analyze_reports_gemini_quota_failures(temp_dir):
    image_path = temp_dir / "front.jpg"
    cv2.imwrite(str(image_path), np.zeros((80, 120, 3), dtype=np.uint8))

    analyzer = GeminiAnalyzer.__new__(GeminiAnalyzer)
    analyzer.model = FakeFailingGeminiModel("429 billing cap exceeded")
    analyzer.api_key = "configured-test-key"
    analyzer.openai_client = None
    analyzer.openai_api_key = None
    analyzer._last_gemini_error = None
    analyzer._last_openai_error = None

    result = analyzer._analyze_sync([str(image_path)])

    assert result["available"] is False
    assert result["reason"] == "Gemini API unavailable: quota, rate limit, or billing cap exceeded"
    assert analyzer.model.calls


class FakeOpenAIResponses:
    def __init__(self, text):
        self.text = text
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return type("OpenAIResponse", (), {"output_text": self.text})()


class FakeOpenAIClient:
    def __init__(self, text):
        self.responses = FakeOpenAIResponses(text)


class FakeFailingOpenAIResponses:
    def create(self, **kwargs):
        raise RuntimeError("responses endpoint not supported")


class FakeOpenAIChatCompletions:
    def __init__(self, text):
        self.text = text
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        message = type("Message", (), {"content": self.text})()
        choice = type("Choice", (), {"message": message})()
        return type("ChatResponse", (), {"choices": [choice]})()


class FakeOpenAIChat:
    def __init__(self, text):
        self.completions = FakeOpenAIChatCompletions(text)


class FakeOpenAIChatOnlyClient:
    def __init__(self, text):
        self.responses = FakeFailingOpenAIResponses()
        self.chat = FakeOpenAIChat(text)


def test_analyze_uses_openai_fallback_when_gemini_unavailable(temp_dir):
    image_path = temp_dir / "front.jpg"
    cv2.imwrite(str(image_path), np.zeros((80, 120, 3), dtype=np.uint8))

    analyzer = GeminiAnalyzer.__new__(GeminiAnalyzer)
    analyzer.model = FakeFailingGeminiModel("429 billing cap exceeded")
    analyzer.api_key = "configured-test-key"
    analyzer.openai_client = FakeOpenAIClient(
        """
        {
          "vehicle": {"type": "car", "brand": "Toyota", "model": "Sienta", "year": "2024", "variant": "X", "confidence": 0.88},
          "per_frame": [{"index": 1, "view": "front", "observations": "front visible", "damage_notes": "none observed", "condition": "good"}],
          "damage_findings": "No visible damage.",
          "damage_items": [],
          "overall_condition": "good",
          "modification_findings": "No obvious modifications.",
          "modification_items": [{"part": "wheels", "status": "stock", "frame_index": 1, "confidence": 0.7, "notes": "factory style"}],
          "reference_image": {"search_query": "Toyota Sienta 2024 official press image"},
          "summary": "Vehicle appears clean."
        }
        """
    )
    analyzer.openai_api_key = "configured-openai-key"
    analyzer.openai_model = "gpt-4.1-mini"
    analyzer._last_gemini_error = None
    analyzer._last_openai_error = None

    result = analyzer._analyze_sync([str(image_path)])

    assert result["available"] is True
    assert result["provider"] == "openai"
    assert result["vehicle"]["brand"] == "Toyota"
    assert result["vehicle"]["variant"] == "X"
    assert analyzer.model.calls
    assert analyzer.openai_client.responses.calls


def test_analyze_uses_openai_chat_fallback_for_compatible_local_servers(temp_dir):
    image_path = temp_dir / "front.jpg"
    cv2.imwrite(str(image_path), np.zeros((80, 120, 3), dtype=np.uint8))

    analyzer = GeminiAnalyzer.__new__(GeminiAnalyzer)
    analyzer.model = FakeFailingGeminiModel("429 billing cap exceeded")
    analyzer.api_key = "configured-test-key"
    analyzer.openai_client = FakeOpenAIChatOnlyClient(
        """
        {
          "vehicle": {"type": "car", "brand": "Toyota", "model": "Sienta", "year": "2024", "variant": "X", "confidence": 0.88},
          "per_frame": [{"index": 1, "view": "front", "observations": "front visible"}],
          "damage_items": [],
          "overall_condition": "good",
          "modification_items": [],
          "reference_image": {"search_query": "Toyota Sienta 2024 official press image"},
          "summary": "Vehicle appears clean."
        }
        """
    )
    analyzer.openai_api_key = "local-openai-compatible"
    analyzer.openai_model = "local-vlm"
    analyzer._last_gemini_error = None
    analyzer._last_openai_error = None

    result = analyzer._analyze_sync([str(image_path)])

    assert result["available"] is True
    assert result["provider"] == "openai"
    assert result["vehicle"]["model"] == "Sienta"
    assert analyzer.openai_client.chat.completions.calls
