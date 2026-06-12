"""Unit tests for the native Ollama client."""

from src.services.ollama_client import OllamaClient


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_normalizes_v1_suffix_and_trailing_slash():
    client = OllamaClient("http://localhost:11434/v1/", "qwen2.5vl", "gemma2:9b")
    assert client.base_url == "http://localhost:11434"
    assert client.available is True


def test_not_configured_is_unavailable():
    client = OllamaClient("", "qwen2.5vl", "gemma2:9b")
    assert client.available is False
    assert client.chat_json("hello") is None
    assert "not configured" in (client.last_error or "")


def test_chat_json_posts_native_endpoint_with_images_and_json_format(monkeypatch, tmp_path):
    image = tmp_path / "frame.jpg"
    image.write_bytes(b"\xff\xd8\xff\xe0fake-jpeg")
    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["body"] = json
        captured["timeout"] = timeout
        return _FakeResponse(200, {"message": {"content": '{"value": 42}'}})

    monkeypatch.setattr("requests.post", fake_post)

    client = OllamaClient("http://localhost:11434", "qwen2.5vl", "gemma2:9b", timeout_seconds=99)
    out = client.chat_json("read it", image_paths=[str(image)], model="qwen2.5vl:7b")

    assert out == '{"value": 42}'
    assert captured["url"] == "http://localhost:11434/api/chat"
    assert captured["timeout"] == 99
    body = captured["body"]
    assert body["model"] == "qwen2.5vl:7b"
    assert body["format"] == "json"
    assert body["stream"] is False
    assert body["messages"][0]["images"], "base64 image should be attached"


def test_chat_json_reports_model_not_found(monkeypatch):
    monkeypatch.setattr(
        "requests.post",
        lambda url, json=None, timeout=None: _FakeResponse(404, {}, "model not found"),
    )
    client = OllamaClient("http://localhost:11434", "missing-model", "gemma2:9b")
    assert client.chat_json("hi") is None
    assert "ollama pull missing-model" in (client.last_error or "")


def test_chat_json_reports_empty_content(monkeypatch):
    monkeypatch.setattr(
        "requests.post",
        lambda url, json=None, timeout=None: _FakeResponse(200, {"message": {"content": "   "}}),
    )
    client = OllamaClient("http://localhost:11434", "qwen2.5vl", "gemma2:9b")
    assert client.chat_json("hi") is None
    assert "no text" in (client.last_error or "")


def test_chat_json_handles_connection_error(monkeypatch):
    import requests

    def boom(url, json=None, timeout=None):
        raise requests.exceptions.ConnectionError("refused")

    monkeypatch.setattr("requests.post", boom)
    client = OllamaClient("http://localhost:11434", "qwen2.5vl", "gemma2:9b")
    assert client.chat_json("hi") is None
    assert "unreachable" in (client.last_error or "")


def test_model_matches_tolerates_implicit_tag():
    assert OllamaClient._model_matches(["qwen2.5vl:7b"], "qwen2.5vl") is True
    assert OllamaClient._model_matches(["gemma2:9b"], "gemma2:9b") is True
    assert OllamaClient._model_matches(["llava:latest"], "qwen2.5vl") is False


def test_list_models(monkeypatch):
    monkeypatch.setattr(
        "requests.get",
        lambda url, timeout=None: _FakeResponse(
            200, {"models": [{"model": "qwen2.5vl:7b"}, {"name": "gemma2:9b"}]}
        ),
    )
    client = OllamaClient("http://localhost:11434", "qwen2.5vl", "gemma2:9b")
    assert client.list_models() == ["qwen2.5vl:7b", "gemma2:9b"]


def test_from_env_reads_config(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://example:11434")
    monkeypatch.setenv("OLLAMA_VISION_MODEL", "qwen2.5vl:7b")
    monkeypatch.setenv("OLLAMA_TEXT_MODEL", "gemma2:9b")
    client = OllamaClient.from_env()
    assert client.base_url == "http://example:11434"
    assert client.vision_model == "qwen2.5vl:7b"
    assert client.text_model == "gemma2:9b"
    assert client.available is True
