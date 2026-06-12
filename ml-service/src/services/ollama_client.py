"""
Native Ollama client for local VLM / LLM inference.

Ollama exposes an OpenAI-compatible ``/v1`` surface, but it does **not**
implement the newer ``/v1/responses`` API and its OpenAI-compatible
chat-completions image handling is finicky. Routing Ollama through the OpenAI
SDK therefore tends to fail closed ("response returned no text") — which is
exactly the failure shown on the inspection page when ``OPENAI_BASE_URL`` is
pointed at Ollama.

This client speaks Ollama's **native** ``/api/chat`` endpoint directly, which:

  * accepts images as base64 strings on the message (reliable for vision
    models such as ``qwen2.5vl``, ``llama3.2-vision``, ``llava``),
  * supports ``format: "json"`` to *force* a valid JSON object — every prompt
    in this service asks for JSON, so this dramatically improves the
    reliability of smaller local models.

Only ``requests`` is needed (already a service dependency). All failures
degrade gracefully: methods return ``None`` and stash a human-readable
``last_error`` so callers can surface a reason and fall back to the next
provider.
"""

from __future__ import annotations

import base64
import logging
import os
from typing import List, Optional

logger = logging.getLogger(__name__)

# Local models on CPU/Metal can be slow on the first (cold) call; be generous.
_DEFAULT_TIMEOUT_SECONDS = 120.0
# Sensible defaults match the models commonly pulled for this project. Both are
# overridable via env — see .env.example.
_DEFAULT_VISION_MODEL = "qwen2.5vl"
_DEFAULT_TEXT_MODEL = "gemma2:9b"


def _clean_env(name: str) -> str:
    return os.getenv(name, "").strip()


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return float(default)
    try:
        return float(raw)
    except ValueError:
        return float(default)


class OllamaClient:
    """Thin wrapper over Ollama's native ``/api/chat`` (and ``/api/tags``)."""

    def __init__(
        self,
        base_url: str,
        vision_model: str,
        text_model: str,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        # Normalize: strip a trailing slash and a trailing OpenAI-compat "/v1"
        # so users can paste either the native base or the /v1 base they used
        # with OPENAI_BASE_URL.
        url = (base_url or "").strip().rstrip("/")
        if url.endswith("/v1"):
            url = url[: -len("/v1")]
        self.base_url = url
        self.vision_model = vision_model or _DEFAULT_VISION_MODEL
        self.text_model = text_model or self.vision_model
        self.timeout_seconds = timeout_seconds
        self.last_error: Optional[str] = None

    @classmethod
    def from_env(cls) -> "OllamaClient":
        return cls(
            base_url=_clean_env("OLLAMA_BASE_URL"),
            vision_model=_clean_env("OLLAMA_VISION_MODEL") or _DEFAULT_VISION_MODEL,
            text_model=(
                _clean_env("OLLAMA_TEXT_MODEL")
                or _clean_env("OLLAMA_VISION_MODEL")
                or _DEFAULT_TEXT_MODEL
            ),
            timeout_seconds=_env_float("OLLAMA_TIMEOUT_SECONDS", _DEFAULT_TIMEOUT_SECONDS),
        )

    @property
    def available(self) -> bool:
        """Configured to be used — i.e. an OLLAMA_BASE_URL was provided."""
        return bool(self.base_url)

    # ------------------------------------------------------------------ #
    # Inference                                                          #
    # ------------------------------------------------------------------ #

    def chat_json(
        self,
        prompt: str,
        *,
        image_paths: Optional[List[str]] = None,
        model: Optional[str] = None,
        force_json: bool = True,
        timeout_seconds: Optional[float] = None,
    ) -> Optional[str]:
        """
        Send a single user turn (text + optional images) to ``/api/chat`` and
        return the assistant message content as a string.

        Returns ``None`` on any failure and sets ``self.last_error`` to a
        human-readable reason (unreachable server, missing model, empty
        response, …) so the caller can degrade gracefully.
        """
        self.last_error = None
        if not self.base_url:
            self.last_error = "Ollama base URL not configured"
            return None

        try:
            import requests
        except Exception as exc:  # pragma: no cover - requests is a hard dep
            self.last_error = f"Ollama unavailable: requests not importable ({exc})"
            return None

        chosen_model = model or self.vision_model
        message: dict = {"role": "user", "content": prompt}
        if image_paths:
            encoded = [enc for enc in (self._encode_image(p) for p in image_paths) if enc]
            if not encoded:
                self.last_error = "Ollama VLM unavailable: no readable images to send"
                return None
            message["images"] = encoded

        payload: dict = {
            "model": chosen_model,
            "messages": [message],
            "stream": False,
            "options": {"temperature": 0},
        }
        if force_json:
            # Force a JSON object. Every prompt in this service requests JSON.
            payload["format"] = "json"

        timeout = timeout_seconds if timeout_seconds is not None else self.timeout_seconds
        try:
            response = requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=timeout,
            )
        except requests.exceptions.ConnectionError as exc:
            self.last_error = (
                f"Ollama unreachable at {self.base_url} — is 'ollama serve' running? ({exc})"
            )
            return None
        except requests.exceptions.Timeout:
            self.last_error = f"Ollama timed out after {timeout:.0f}s on model '{chosen_model}'"
            return None
        except Exception as exc:
            self.last_error = f"Ollama request failed: {exc}"
            return None

        if response.status_code == 404:
            # Ollama returns 404 with a "model not found" body when the tag
            # hasn't been pulled.
            self.last_error = (
                f"Ollama model '{chosen_model}' not found — run 'ollama pull {chosen_model}'"
            )
            return None
        if response.status_code >= 400:
            self.last_error = f"Ollama HTTP {response.status_code}: {response.text[:200]}"
            return None

        try:
            data = response.json()
        except Exception as exc:
            self.last_error = f"Ollama returned a non-JSON envelope: {exc}"
            return None

        content = ((data or {}).get("message") or {}).get("content")
        if not isinstance(content, str) or not content.strip():
            self.last_error = "Ollama VLM unavailable: response returned no text"
            return None
        return content.strip()

    # ------------------------------------------------------------------ #
    # Health                                                             #
    # ------------------------------------------------------------------ #

    def list_models(self, *, timeout_seconds: float = 5.0) -> Optional[List[str]]:
        """Return the names of locally-available models, or ``None`` if the
        server cannot be reached. Sets ``self.last_error`` on failure."""
        self.last_error = None
        if not self.base_url:
            self.last_error = "Ollama base URL not configured"
            return None
        try:
            import requests

            response = requests.get(f"{self.base_url}/api/tags", timeout=timeout_seconds)
            response.raise_for_status()
            data = response.json() or {}
        except Exception as exc:
            self.last_error = f"Ollama unreachable at {self.base_url}: {exc}"
            return None
        models = data.get("models")
        if not isinstance(models, list):
            return []
        return [m.get("model") or m.get("name") for m in models if isinstance(m, dict)]

    @staticmethod
    def _model_matches(available: List[str], wanted: str) -> bool:
        """Match a wanted model against ``ollama list`` names, tolerating the
        implicit ``:latest`` tag (e.g. wanted 'qwen2.5vl' matches
        'qwen2.5vl:7b' or 'qwen2.5vl:latest')."""
        wanted = (wanted or "").strip()
        if not wanted:
            return False
        wanted_base = wanted.split(":", 1)[0]
        for name in available:
            if not name:
                continue
            if name == wanted:
                return True
            if name.split(":", 1)[0] == wanted_base:
                return True
        return False

    @staticmethod
    def _encode_image(path: str) -> Optional[str]:
        try:
            with open(path, "rb") as image_file:
                return base64.b64encode(image_file.read()).decode("ascii")
        except Exception as exc:
            logger.warning("Ollama: could not read image %s: %s", path, exc)
            return None
