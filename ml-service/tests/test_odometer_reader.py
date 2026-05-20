import cv2
import numpy as np

import src.services.odometer_reader as odometer_module
from src.services.odometer_reader import OdometerReader


def test_odometer_reader_accepts_openai_compatible_base_url_without_public_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:11434/v1")

    reader = OdometerReader()

    assert reader.openai_client is not None
    assert reader.openai_api_key == "local-openai-compatible"
    assert reader.openai_base_url == "http://localhost:11434/v1"
    assert reader.use_openai is True


class FakeResponse:
    def __init__(self, text):
        self.text = text


class FakeGeminiModel:
    def __init__(self, text):
        self.text = text
        self.calls = []

    def generate_content(self, content):
        self.calls.append(content)
        return FakeResponse(self.text)


class FakeFailingGeminiModel:
    def __init__(self, error):
        self.error = error
        self.calls = []

    def generate_content(self, content):
        self.calls.append(content)
        raise RuntimeError(self.error)


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


def _reader_with_fake_gemini(text=None, model=None):
    reader = OdometerReader.__new__(OdometerReader)
    reader.use_gemini = True
    reader.use_openai = False
    reader.ocr_available = False
    reader.use_paddle = False
    reader.gemini_model = model or FakeGeminiModel(text)
    reader._last_openai_error = None
    return reader


def _reader_with_fake_openai(text):
    reader = OdometerReader.__new__(OdometerReader)
    reader.use_gemini = False
    reader.use_openai = True
    reader.ocr_available = False
    reader.use_paddle = False
    reader.openai_client = FakeOpenAIClient(text)
    reader.openai_api_key = "configured-openai-key"
    reader.openai_model = "gpt-4.1-mini"
    reader._last_gemini_error = None
    reader._last_openai_error = None
    return reader


def _reader_with_fake_openai_chat(text):
    reader = OdometerReader.__new__(OdometerReader)
    reader.use_gemini = False
    reader.use_openai = True
    reader.ocr_available = False
    reader.use_paddle = False
    reader.openai_client = FakeOpenAIChatOnlyClient(text)
    reader.openai_api_key = "local-openai-compatible"
    reader.openai_model = "local-vlm"
    reader._last_gemini_error = None
    reader._last_openai_error = None
    return reader


def test_gemini_vision_fallback_reads_odometer_when_ocr_unavailable(temp_dir):
    image_path = temp_dir / "dashboard.jpg"
    image = np.zeros((120, 220, 3), dtype=np.uint8)
    cv2.putText(image, "ODO 123456", (18, 68), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    cv2.imwrite(str(image_path), image)

    reader = _reader_with_fake_gemini('{"value": 123456, "confidence": 0.91, "reasoning": "visible ODO"}')
    result = reader._read_sync([str(image_path)])

    assert result["value"] == 123456
    assert result["confidence"] == 0.91
    assert result["speedometer_image_path"] == str(image_path)
    assert result["source"] == "gemini_vision"
    assert reader.gemini_model.calls
    assert len(reader.gemini_model.calls[0]) == 2


def test_openai_vision_fallback_reads_odometer_when_ocr_and_gemini_unavailable(temp_dir):
    image_path = temp_dir / "dashboard.jpg"
    cv2.imwrite(str(image_path), np.zeros((80, 120, 3), dtype=np.uint8))

    reader = _reader_with_fake_openai('{"value": 12292, "confidence": 0.84, "reasoning": "visible ODO"}')
    result = reader._read_sync([str(image_path)])

    assert result["value"] == 12292
    assert result["confidence"] == 0.84
    assert result["speedometer_image_path"] == str(image_path)
    assert result["source"] == "openai_vision"
    assert reader.openai_client.responses.calls


def test_openai_chat_fallback_reads_odometer_for_compatible_local_servers(temp_dir):
    image_path = temp_dir / "dashboard.jpg"
    cv2.imwrite(str(image_path), np.zeros((80, 120, 3), dtype=np.uint8))

    reader = _reader_with_fake_openai_chat('{"value": 12292, "confidence": 0.84, "reasoning": "visible ODO"}')
    result = reader._read_sync([str(image_path)])

    assert result["value"] == 12292
    assert result["confidence"] == 0.84
    assert result["source"] == "openai_vision"
    assert reader.openai_client.chat.completions.calls


def test_parse_gemini_odometer_json_handles_markdown_and_null():
    parsed = OdometerReader._parse_gemini_odometer_json(
        '```json\n{"value": null, "confidence": 0.2, "reasoning": "not visible"}\n```',
        "frame.jpg",
    )

    assert parsed == {
        "value": None,
        "confidence": 0.2,
        "frame": "frame.jpg",
        "reasoning": "not visible",
    }


def test_gemini_vision_fallback_ignores_out_of_range_values(temp_dir):
    image_path = temp_dir / "dashboard.jpg"
    cv2.imwrite(str(image_path), np.zeros((80, 120, 3), dtype=np.uint8))

    reader = _reader_with_fake_gemini('{"value": 99999999, "confidence": 0.95, "reasoning": "bad"}')
    result = reader._read_sync([str(image_path)])

    assert result["value"] is None
    assert result["confidence"] == 0.0
    assert result["speedometer_image_path"] == str(image_path)


def test_gemini_vision_fallback_reports_quota_failures(temp_dir):
    image_path = temp_dir / "dashboard.jpg"
    cv2.imwrite(str(image_path), np.zeros((80, 120, 3), dtype=np.uint8))

    model = FakeFailingGeminiModel("429 billing cap exceeded")
    reader = _reader_with_fake_gemini(model=model)
    result = reader._read_sync([str(image_path)])

    assert result["value"] is None
    assert result["confidence"] == 0.0
    assert result["speedometer_image_path"] == str(image_path)
    assert result["source"] == "gemini_vision"
    assert result["reason"] == "Gemini API unavailable: quota, rate limit, or billing cap exceeded"
    assert model.calls


def test_ocr_ranking_downgrades_single_conflicting_readings():
    readings = [
        {"value": 112028, "confidence": 0.88, "frame": "a.jpg", "preprocessing": "thresholded", "digit_count": 6},
        {"value": 9230, "confidence": 0.88, "frame": "a.jpg", "preprocessing": "enhanced", "digit_count": 4},
        {"value": 42081, "confidence": 0.80, "frame": "b.jpg", "preprocessing": "grayscale", "digit_count": 5},
    ]

    ranked = OdometerReader._rank_ocr_readings(readings)

    assert ranked[0]["value"] == 112028
    assert ranked[0]["confidence"] < 0.5
    assert ranked[0]["occurrences"] == 1


def test_openai_validates_ocr_candidates_when_gemini_unavailable():
    reader = _reader_with_fake_openai('{"value": 12292, "confidence": 0.88, "reasoning": "best match"}')
    reader.ocr_available = True

    result = reader._validate_ocr_readings_with_vlm(
        [{"value": 12292, "confidence": 0.42, "source_text": "ODO 12292", "preprocessing": "original", "digit_count": 5}],
        [{"text": "ODO 12292", "confidence": 0.8, "preprocessing": "original"}],
        "dashboard.jpg",
        ["dashboard.jpg"],
    )

    assert result["value"] == 12292
    assert result["confidence"] == 0.88
    assert result["frame"] == "dashboard.jpg"
    assert reader.openai_client.responses.calls


def test_local_ocr_low_confidence_result_includes_verification_reason(temp_dir, monkeypatch):
    image_a = temp_dir / "dashboard_a.jpg"
    image_b = temp_dir / "dashboard_b.jpg"
    cv2.imwrite(str(image_a), np.zeros((80, 160, 3), dtype=np.uint8))
    cv2.imwrite(str(image_b), np.zeros((80, 160, 3), dtype=np.uint8))

    class FakeTesseract:
        @staticmethod
        def image_to_string(image, config=None, timeout=None):
            if "--psm 6" not in (config or ""):
                return ""
            if str(getattr(image, "filename", "")).endswith("dashboard_a.jpg"):
                return "112028"
            return "9230"

    reader = OdometerReader.__new__(OdometerReader)
    reader.ocr_available = True
    reader.use_gemini = False
    reader.use_openai = False
    reader.use_paddle = False
    reader.tesseract_config = r"--oem 3 --psm 6 -c tessedit_char_whitelist=0123456789"

    monkeypatch.setattr(odometer_module, "TESSERACT_AVAILABLE", True)
    monkeypatch.setattr(odometer_module, "pytesseract", FakeTesseract)
    monkeypatch.setattr(
        reader,
        "_preprocess_image",
        lambda frame_path: [(str(image_a), "original"), (str(image_b), "enhanced")],
    )

    result = reader._read_sync([str(image_a)])

    assert result["source"] == "local_ocr"
    assert result["confidence"] < 0.5
    assert "manual/VLM verification" in result["reason"]
