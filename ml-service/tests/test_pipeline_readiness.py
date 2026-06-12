import asyncio

from src.services import pipeline_readiness
from src.services.pipeline_readiness import build_pipeline_readiness


class FakeRegistry:
    is_initialized = True


class FakeUninitializedRegistry:
    is_initialized = False


def _fake_modules(missing=None):
    missing = set(missing or [])

    def available(name):
        return name not in missing

    return available


def test_pipeline_readiness_reports_ready_when_required_paths_exist(monkeypatch):
    monkeypatch.setattr(pipeline_readiness, "_module_available", _fake_modules())
    monkeypatch.setattr(pipeline_readiness, "_env_api_key_present", lambda name: True)
    monkeypatch.setattr(pipeline_readiness.shutil, "which", lambda name: "/usr/bin/tesseract")

    result = build_pipeline_readiness(model_registry=FakeRegistry())

    assert result["status"] == "ready"
    assert result["capabilities"]["model_backed_angle_scoring"] is True
    assert result["capabilities"]["odometer_reading"] is True
    assert result["capabilities"]["llm_vlm_analysis"] is True
    assert result["missing_required"] == []
    assert any("not live-verified" in warning for warning in result["warnings"])


def test_pipeline_readiness_can_require_startup_loaded_models(monkeypatch):
    monkeypatch.setattr(pipeline_readiness, "_module_available", _fake_modules())
    monkeypatch.setattr(pipeline_readiness, "_env_api_key_present", lambda name: True)
    monkeypatch.setattr(pipeline_readiness.shutil, "which", lambda name: "/usr/bin/tesseract")

    result = build_pipeline_readiness(
        model_registry=FakeUninitializedRegistry(),
        require_loaded_models=True,
    )

    assert result["status"] == "degraded"
    assert result["capabilities"]["model_backed_angle_scoring"] is False
    assert result["checks"]["model_registry"]["required_for_startup_loaded_models"] is True
    assert result["missing_required"] == ["model_backed_angle_scoring"]


def test_pipeline_readiness_degrades_when_odometer_and_gemini_paths_missing(monkeypatch):
    # Isolate from any base-url provider leaking in from a developer .env.
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    missing = {"paddleocr", "pytesseract", "google.generativeai", "openai"}
    monkeypatch.setattr(pipeline_readiness, "_module_available", _fake_modules(missing))
    monkeypatch.setattr(pipeline_readiness, "_env_api_key_present", lambda name: False)
    monkeypatch.setattr(pipeline_readiness.shutil, "which", lambda name: None)

    result = build_pipeline_readiness(model_registry=FakeRegistry())

    assert result["status"] == "degraded"
    assert result["capabilities"]["frame_organization"] is True
    assert result["capabilities"]["odometer_reading"] is False
    assert result["capabilities"]["llm_vlm_analysis"] is False
    assert result["missing_required"] == ["odometer_reading", "llm_vlm_analysis"]


def test_pipeline_readiness_live_gemini_failure_blocks_vlm_and_fallback_odometer(monkeypatch):
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.setattr(pipeline_readiness, "_module_available", _fake_modules({"paddleocr", "pytesseract"}))
    monkeypatch.setattr(pipeline_readiness, "_env_api_key_present", lambda name: name != "OPENAI_API_KEY")
    monkeypatch.setattr(pipeline_readiness.shutil, "which", lambda name: None)
    monkeypatch.setattr(
        pipeline_readiness,
        "_check_gemini_live",
        lambda enabled, timeout_seconds: {
            "ready": False,
            "reason": "Gemini API unavailable: quota exceeded",
        },
    )

    result = build_pipeline_readiness(model_registry=FakeRegistry(), live_gemini=True)

    assert result["status"] == "degraded"
    assert result["capabilities"]["odometer_reading"] is False
    assert result["capabilities"]["llm_vlm_analysis"] is False
    assert result["checks"]["gemini"]["live"]["reason"] == "Gemini API unavailable: quota exceeded"


def test_pipeline_readiness_accepts_openai_vlm_fallback_when_gemini_missing(monkeypatch):
    monkeypatch.setattr(pipeline_readiness, "_module_available", _fake_modules({"google.generativeai"}))
    monkeypatch.setattr(
        pipeline_readiness,
        "_env_api_key_present",
        lambda name: name == "OPENAI_API_KEY",
    )
    monkeypatch.setattr(pipeline_readiness.shutil, "which", lambda name: "/usr/bin/tesseract")

    result = build_pipeline_readiness(model_registry=FakeRegistry())

    assert result["status"] == "ready"
    assert result["capabilities"]["llm_vlm_analysis"] is True
    assert result["checks"]["gemini"]["ready"] is False
    assert result["checks"]["openai"]["ready"] is True


def test_pipeline_readiness_accepts_openai_compatible_base_url_without_public_key(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(pipeline_readiness, "_module_available", _fake_modules({"google.generativeai"}))
    monkeypatch.setattr(pipeline_readiness, "_env_api_key_present", lambda name: False)
    monkeypatch.setattr(pipeline_readiness.shutil, "which", lambda name: "/usr/bin/tesseract")

    result = build_pipeline_readiness(model_registry=FakeRegistry())

    assert result["status"] == "ready"
    assert result["capabilities"]["llm_vlm_analysis"] is True
    assert result["checks"]["openai"]["ready"] is True
    assert result["checks"]["openai"]["api_key_configured"] is True
    assert result["checks"]["openai"]["base_url"] == "http://localhost:11434/v1"


def test_pipeline_readiness_live_openai_failure_blocks_openai_only_vlm(monkeypatch):
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.setattr(
        pipeline_readiness,
        "_module_available",
        _fake_modules({"google.generativeai", "paddleocr", "pytesseract"}),
    )
    monkeypatch.setattr(
        pipeline_readiness,
        "_env_api_key_present",
        lambda name: name == "OPENAI_API_KEY",
    )
    monkeypatch.setattr(pipeline_readiness.shutil, "which", lambda name: None)
    monkeypatch.setattr(
        pipeline_readiness,
        "_check_openai_live",
        lambda enabled, timeout_seconds: {
            "ready": False,
            "reason": "OpenAI API unavailable: quota exceeded",
        },
    )

    result = build_pipeline_readiness(model_registry=FakeRegistry(), live_openai=True)

    assert result["status"] == "degraded"
    assert result["capabilities"]["odometer_reading"] is False
    assert result["capabilities"]["llm_vlm_analysis"] is False
    assert result["checks"]["openai"]["live"]["reason"] == "OpenAI API unavailable: quota exceeded"


def test_pipeline_readiness_live_openai_success_accepts_fallback(monkeypatch):
    monkeypatch.setattr(
        pipeline_readiness,
        "_module_available",
        _fake_modules({"google.generativeai", "paddleocr", "pytesseract"}),
    )
    monkeypatch.setattr(
        pipeline_readiness,
        "_env_api_key_present",
        lambda name: name == "OPENAI_API_KEY",
    )
    monkeypatch.setattr(pipeline_readiness.shutil, "which", lambda name: None)
    monkeypatch.setattr(
        pipeline_readiness,
        "_check_openai_live",
        lambda enabled, timeout_seconds: {
            "ready": True,
            "reason": None,
            "model": "gpt-4.1-mini",
        },
    )

    result = build_pipeline_readiness(model_registry=FakeRegistry(), live_openai=True)

    assert result["status"] == "ready"
    assert result["capabilities"]["odometer_reading"] is True
    assert result["capabilities"]["llm_vlm_analysis"] is True
    assert result["checks"]["openai"]["live"]["ready"] is True


def test_pipeline_readiness_live_openai_accepts_chat_completion_fallback(monkeypatch):
    monkeypatch.setattr(
        pipeline_readiness,
        "_module_available",
        _fake_modules({"google.generativeai", "paddleocr", "pytesseract"}),
    )
    monkeypatch.setattr(
        pipeline_readiness,
        "_env_api_key_present",
        lambda name: name == "OPENAI_API_KEY",
    )
    monkeypatch.setattr(pipeline_readiness.shutil, "which", lambda name: None)
    monkeypatch.setattr(
        pipeline_readiness,
        "_call_openai_responses_ready",
        lambda client, model, timeout_seconds: (_ for _ in ()).throw(RuntimeError("responses not supported")),
    )
    monkeypatch.setattr(
        pipeline_readiness,
        "_call_openai_chat_ready",
        lambda client, model, timeout_seconds: type("ChatResponse", (), {"choices": [object()]})(),
    )

    result = build_pipeline_readiness(model_registry=FakeRegistry(), live_openai=True)

    assert result["status"] == "ready"
    assert result["capabilities"]["llm_vlm_analysis"] is True
    assert result["checks"]["openai"]["live"]["ready"] is True


def test_pipeline_readiness_warns_when_odometer_relies_on_unverified_gemini(monkeypatch):
    monkeypatch.setattr(pipeline_readiness, "_module_available", _fake_modules({"paddleocr", "pytesseract"}))
    monkeypatch.setattr(pipeline_readiness, "_env_api_key_present", lambda name: True)
    monkeypatch.setattr(pipeline_readiness.shutil, "which", lambda name: None)

    result = build_pipeline_readiness(model_registry=FakeRegistry())

    assert result["status"] == "ready"
    assert result["capabilities"]["odometer_reading"] is True
    assert any("Odometer reading is relying on VLM fallback" in warning for warning in result["warnings"])


def test_pipeline_readiness_accepts_openai_odometer_fallback_without_local_ocr(monkeypatch):
    monkeypatch.setattr(
        pipeline_readiness,
        "_module_available",
        _fake_modules({"paddleocr", "pytesseract", "google.generativeai"}),
    )
    monkeypatch.setattr(
        pipeline_readiness,
        "_env_api_key_present",
        lambda name: name == "OPENAI_API_KEY",
    )
    monkeypatch.setattr(pipeline_readiness.shutil, "which", lambda name: None)

    result = build_pipeline_readiness(model_registry=FakeRegistry())

    assert result["status"] == "ready"
    assert result["capabilities"]["odometer_reading"] is True
    assert result["capabilities"]["llm_vlm_analysis"] is True
    assert result["checks"]["openai"]["ready"] is True


def test_ready_endpoint_forwards_live_openai(monkeypatch):
    from src import main as ml_main

    captured = {}

    def fake_build_pipeline_readiness(**kwargs):
        captured.update(kwargs)
        return {"status": "ready", "capabilities": {"llm_vlm_analysis": True}}

    monkeypatch.setattr(ml_main, "build_pipeline_readiness", fake_build_pipeline_readiness)
    monkeypatch.setattr(ml_main.app.state, "model_registry", FakeRegistry(), raising=False)

    result = asyncio.run(ml_main.readiness_check(live_gemini=True, live_openai=True))

    assert result["status"] == "ready"
    assert captured["require_loaded_models"] is True
    assert captured["live_gemini"] is True
    assert captured["live_openai"] is True
