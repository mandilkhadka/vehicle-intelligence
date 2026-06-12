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
                    # >= ML_DAMAGE_VLM_HIGH_CONFIDENCE so this single-frame item
                    # survives the multi-frame consensus gate.
                    "confidence": "0.9",
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
            # The prompt schema says "moderate"; ingest normalizes it to the
            # shared DamageSeverity contract value "medium".
            "severity": "medium",
            "frame_index": 1,
            "confidence": 0.9,
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


class FakeOllamaClient:
    def __init__(self, text):
        self.available = True
        self.vision_model = "qwen2.5vl"
        self.text_model = "gemma2:9b"
        self.timeout_seconds = 120.0
        self.last_error = None
        self._text = text
        self.calls = []

    def chat_json(self, prompt, *, image_paths=None, model=None, force_json=True, timeout_seconds=None):
        self.calls.append({"image_paths": image_paths, "model": model, "timeout_seconds": timeout_seconds})
        return self._text


def test_analyze_prefers_ollama_when_configured(temp_dir):
    image_path = temp_dir / "front.jpg"
    cv2.imwrite(str(image_path), np.zeros((80, 120, 3), dtype=np.uint8))

    analyzer = GeminiAnalyzer.__new__(GeminiAnalyzer)
    analyzer.ollama = FakeOllamaClient(
        '{"vehicle": {"type": "car", "brand": "Toyota", "model": "Sienta", "year": "2024", "confidence": 0.9},'
        '"per_frame": [{"index": 1, "view": "front", "observations": "front visible"}],'
        '"damage_items": [], "overall_condition": "good", "modification_items": [],'
        '"reference_image": {"search_query": "Toyota Sienta 2024 official press image"},'
        '"summary": "Vehicle appears clean."}'
    )
    # No cloud providers — Ollama must be enough on its own.
    analyzer.model = None
    analyzer.api_key = None
    analyzer.openai_client = None
    analyzer.openai_api_key = None
    analyzer._last_gemini_error = None
    analyzer._last_openai_error = None

    result = analyzer._analyze_sync([str(image_path)])

    assert result["available"] is True
    assert result["provider"] == "ollama"
    assert result["vehicle"]["brand"] == "Toyota"
    # Ollama received the frame path, not a PIL image / OpenAI selection.
    assert analyzer.ollama.calls
    assert analyzer.ollama.calls[0]["image_paths"] == [str(image_path)]


def test_analyze_caps_ollama_call_timeout_below_stage_budget(temp_dir, monkeypatch):
    """A hung Ollama must not consume the whole gemini stage budget (120s);
    the per-call timeout is capped so cloud fallbacks still get a chance."""
    monkeypatch.delenv("OLLAMA_ANALYZE_TIMEOUT_SECONDS", raising=False)
    image_path = temp_dir / "front.jpg"
    cv2.imwrite(str(image_path), np.zeros((80, 120, 3), dtype=np.uint8))

    analyzer = GeminiAnalyzer.__new__(GeminiAnalyzer)
    analyzer.ollama = FakeOllamaClient(
        '{"vehicle": {"type": "car", "brand": "Toyota", "confidence": 0.9},'
        '"per_frame": [], "damage_items": [], "modification_items": [],'
        '"reference_image": {}, "summary": "ok"}'
    )
    analyzer.model = None
    analyzer.api_key = None
    analyzer.openai_client = None
    analyzer.openai_api_key = None
    analyzer._last_gemini_error = None
    analyzer._last_openai_error = None

    analyzer._analyze_sync([str(image_path)])

    timeout = analyzer.ollama.calls[0]["timeout_seconds"]
    assert timeout is not None
    assert 0 < timeout <= 60.0


def test_normalize_matches_per_frame_entries_by_index_not_position():
    """Local models skip/reorder per_frame entries; pairing must use the
    explicit 1-based "index" field, not the list position."""
    analyzer = GeminiAnalyzer.__new__(GeminiAnalyzer)
    parsed = {
        "vehicle": {},
        "per_frame": [
            {"index": 3, "view": "left", "observations": "left side", "condition": "good"},
            {"index": 1, "view": "front", "observations": "front view", "condition": "fair"},
            # frame 2 skipped entirely by the model
        ],
    }
    used_selection = [
        {"frame": "f1.jpg", "view": "front"},
        {"frame": "f2.jpg", "view": "rear"},
        {"frame": "f3.jpg", "view": "left"},
    ]

    result = analyzer._normalize(parsed, used_selection, "{}")

    per_frame = result["per_frame"]
    assert per_frame[0]["frame"] == "f1.jpg"
    assert per_frame[0]["observations"] == "front view"
    assert per_frame[1]["frame"] == "f2.jpg"
    assert per_frame[1]["observations"] is None  # skipped frame stays empty
    assert per_frame[2]["frame"] == "f3.jpg"
    assert per_frame[2]["observations"] == "left side"


def test_normalize_falls_back_to_positional_pairing_without_index_fields():
    analyzer = GeminiAnalyzer.__new__(GeminiAnalyzer)
    parsed = {
        "vehicle": {},
        "per_frame": [
            {"view": "front", "observations": "first"},
            {"view": "rear", "observations": "second"},
        ],
    }
    used_selection = [{"frame": "f1.jpg", "view": "front"}, {"frame": "f2.jpg", "view": "rear"}]

    result = analyzer._normalize(parsed, used_selection, "{}")

    assert result["per_frame"][0]["observations"] == "first"
    assert result["per_frame"][1]["observations"] == "second"


def test_normalize_region_rejects_non_finite_and_clamps_negatives():
    assert GeminiAnalyzer._normalize_region([float("nan"), 1, 2, 3]) is None
    assert GeminiAnalyzer._normalize_region([float("inf"), 1, 2, 3]) is None
    assert GeminiAnalyzer._normalize_region([-5, 100, 300, 400]) == [0.0, 100.0, 300.0, 400.0]


def test_analyze_falls_back_to_gemini_when_ollama_fails(temp_dir):
    image_path = temp_dir / "front.jpg"
    cv2.imwrite(str(image_path), np.zeros((80, 120, 3), dtype=np.uint8))

    failing_ollama = FakeOllamaClient(None)  # chat_json returns None -> fall through
    failing_ollama.last_error = "Ollama unreachable at http://localhost:11434"

    analyzer = GeminiAnalyzer.__new__(GeminiAnalyzer)
    analyzer.ollama = failing_ollama
    analyzer.model = FakeFailingGeminiModel("429 billing cap exceeded")
    analyzer.api_key = "configured-test-key"
    analyzer.openai_client = None
    analyzer.openai_api_key = None
    analyzer._last_gemini_error = None
    analyzer._last_openai_error = None

    result = analyzer._analyze_sync([str(image_path)])

    assert result["available"] is False
    # The combined reason surfaces both the Ollama and Gemini failures.
    assert "Ollama unreachable" in result["reason"]
    assert "quota, rate limit, or billing cap exceeded" in result["reason"]
    assert analyzer.model.calls  # Gemini was attempted after Ollama failed


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


def test_normalize_damage_items_drops_low_confidence(monkeypatch):
    monkeypatch.setenv("ML_DAMAGE_VLM_MIN_CONFIDENCE", "0.55")
    monkeypatch.setenv("ML_DAMAGE_CONSENSUS_MIN_FRAMES", "1")
    items = [
        {"type": "scratch", "location": "left door", "frame_index": 1,
         "confidence": 0.40, "notes": "faint mark"},
    ]
    assert GeminiAnalyzer._normalize_damage_items(items) == []


def test_normalize_damage_items_requires_evidence(monkeypatch):
    monkeypatch.setenv("ML_DAMAGE_VLM_MIN_CONFIDENCE", "0.55")
    monkeypatch.setenv("ML_DAMAGE_CONSENSUS_MIN_FRAMES", "1")
    items = [
        {"type": "dent", "location": "hood", "frame_index": 1, "confidence": 0.95, "notes": "   "},
        {"type": "dent", "location": "hood", "frame_index": 1, "confidence": 0.95},
    ]
    assert GeminiAnalyzer._normalize_damage_items(items) == []


def test_normalize_damage_items_consensus_requires_two_frames(monkeypatch):
    monkeypatch.setenv("ML_DAMAGE_VLM_MIN_CONFIDENCE", "0.55")
    monkeypatch.setenv("ML_DAMAGE_CONSENSUS_MIN_FRAMES", "2")
    monkeypatch.setenv("ML_DAMAGE_VLM_HIGH_CONFIDENCE", "0.85")

    # A mid-confidence finding seen in only one frame looks like a reflection — dropped.
    single = [{"type": "scratch", "location": "left door", "frame_index": 1,
               "confidence": 0.7, "notes": "thin line"}]
    assert GeminiAnalyzer._normalize_damage_items(single) == []

    # The same damage seen from two angles is real — kept and collapsed to the
    # highest-confidence representative.
    two = [
        {"type": "scratch", "location": "left door", "frame_index": 1, "confidence": 0.7, "notes": "scratch a"},
        {"type": "scratch", "location": "Left Door", "frame_index": 2, "confidence": 0.8, "notes": "scratch b"},
    ]
    kept = GeminiAnalyzer._normalize_damage_items(two)
    assert len(kept) == 1
    assert kept[0]["confidence"] == 0.8


def test_normalize_damage_items_high_confidence_single_frame_kept(monkeypatch):
    monkeypatch.setenv("ML_DAMAGE_VLM_MIN_CONFIDENCE", "0.55")
    monkeypatch.setenv("ML_DAMAGE_CONSENSUS_MIN_FRAMES", "2")
    monkeypatch.setenv("ML_DAMAGE_VLM_HIGH_CONFIDENCE", "0.85")
    items = [{"type": "rust", "location": "rear wheel arch", "frame_index": 1,
              "confidence": 0.9, "notes": "orange corrosion, distinct from dirt"}]
    kept = GeminiAnalyzer._normalize_damage_items(items)
    assert len(kept) == 1
    assert kept[0]["type"] == "rust"


def test_normalize_damage_items_parses_and_validates_region(monkeypatch):
    monkeypatch.setenv("ML_DAMAGE_CONSENSUS_MIN_FRAMES", "1")
    monkeypatch.setenv("ML_DAMAGE_VLM_HIGH_CONFIDENCE", "0.85")
    good = [{"type": "dent", "location": "hood", "frame_index": 1, "confidence": 0.9,
             "notes": "dent", "region": [100, 200, 300, 400]}]
    assert GeminiAnalyzer._normalize_damage_items(good)[0]["region"] == [100.0, 200.0, 300.0, 400.0]
    bad = [{"type": "dent", "location": "roof", "frame_index": 1, "confidence": 0.9,
            "notes": "dent", "region": [1, 2, 3]}]
    assert "region" not in GeminiAnalyzer._normalize_damage_items(bad)[0]


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
