"""
Runtime readiness checks for the vehicle video-understanding pipeline.

These checks avoid loading large models by default. They verify the dependency
and configuration paths that decide whether the full inspection pipeline can run.
"""

from __future__ import annotations

import importlib.util
import os
import platform
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Any, Dict, Optional

from src.config.constants import FRAME_EXTRACTION, MODELS


def _module_available(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def _env_api_key_present(name: str) -> bool:
    return len(os.getenv(name, "").strip()) >= 20


def _openai_base_url() -> str:
    return os.getenv("OPENAI_BASE_URL", "").strip()


def _openai_provider_configured() -> bool:
    return _env_api_key_present("OPENAI_API_KEY") or bool(_openai_base_url())


def build_pipeline_readiness(
    *,
    model_registry: Optional[Any] = None,
    require_loaded_models: bool = False,
    live_gemini: bool = False,
    live_openai: bool = False,
    gemini_timeout_seconds: int = 10,
    openai_timeout_seconds: int = 10,
) -> Dict[str, Any]:
    """Return readiness/capability diagnostics for the inspection pipeline."""
    python_ready = sys.version_info >= (3, 10)
    cv_ready = _module_available("cv2")
    numpy_ready = _module_available("numpy")
    pillow_ready = _module_available("PIL")
    yolo_dependency_ready = _module_available("ultralytics")
    torch_ready = _module_available("torch")
    transformers_ready = _module_available("transformers")
    clip_dependency_ready = torch_ready and transformers_ready and pillow_ready
    gemini_library_ready = _module_available("google.generativeai")
    gemini_key_ready = _env_api_key_present("GEMINI_API_KEY")
    gemini_ready = gemini_library_ready and gemini_key_ready
    openai_library_ready = _module_available("openai")
    openai_key_ready = _openai_provider_configured()
    openai_base_url = _openai_base_url()
    openai_ready = openai_library_ready and openai_key_ready

    paddleocr_ready = _module_available("paddleocr")
    pytesseract_ready = _module_available("pytesseract")
    tesseract_binary = shutil.which("tesseract")
    tesseract_ready = pytesseract_ready and bool(tesseract_binary)
    ocr_ready = paddleocr_ready or tesseract_ready

    model_registry_initialized = bool(getattr(model_registry, "is_initialized", False))
    if require_loaded_models:
        model_backed_angle_scoring_ready = model_registry_initialized
    else:
        model_backed_angle_scoring_ready = (
            model_registry_initialized or (yolo_dependency_ready and clip_dependency_ready)
        )
    odometer_ready = ocr_ready or gemini_ready or openai_ready
    llm_vlm_ready = gemini_ready or openai_ready
    frame_organization_ready = python_ready and cv_ready and numpy_ready and pillow_ready

    gemini_live_check = None
    if live_gemini:
        gemini_live_check = _check_gemini_live(
            enabled=gemini_ready,
            timeout_seconds=gemini_timeout_seconds,
        )

    openai_live_check = None
    if live_openai:
        openai_live_check = _check_openai_live(
            enabled=openai_ready,
            timeout_seconds=openai_timeout_seconds,
        )

    if live_gemini or live_openai:
        gemini_provider_ready = (
            gemini_ready and gemini_live_check["ready"]
            if live_gemini and gemini_live_check is not None
            else gemini_ready
        )
        openai_provider_ready = (
            openai_ready and openai_live_check["ready"]
            if live_openai and openai_live_check is not None
            else openai_ready
        )
        llm_vlm_ready = gemini_provider_ready or openai_provider_ready
        if not ocr_ready:
            odometer_ready = gemini_provider_ready or openai_provider_ready

    capabilities = {
        "frame_extraction": frame_organization_ready,
        "frame_organization": frame_organization_ready,
        "model_backed_angle_scoring": model_backed_angle_scoring_ready,
        "odometer_reading": odometer_ready,
        "llm_vlm_analysis": llm_vlm_ready,
    }
    required_ready = all(capabilities.values())
    degraded = frame_organization_ready and not required_ready

    checks = {
        "python": {
            "ready": python_ready,
            "version": platform.python_version(),
            "required": ">=3.10",
        },
        "opencv": {"ready": cv_ready, "module": "cv2"},
        "numpy": {"ready": numpy_ready, "module": "numpy"},
        "pillow": {"ready": pillow_ready, "module": "PIL"},
        "yolo": {
            "ready": yolo_dependency_ready,
            "module": "ultralytics",
            "model": MODELS["yolo"],
        },
        "clip": {
            "ready": clip_dependency_ready,
            "modules": {
                "torch": torch_ready,
                "transformers": transformers_ready,
                "PIL": pillow_ready,
            },
            "model": MODELS["clip"],
        },
        "model_registry": {
            "ready": model_registry_initialized,
            "required_for_startup_loaded_models": require_loaded_models,
        },
        "ocr": {
            "ready": ocr_ready,
            "paddleocr": paddleocr_ready,
            "pytesseract": pytesseract_ready,
            "tesseract_binary": tesseract_binary,
        },
        "gemini": {
            "ready": gemini_ready,
            "library": gemini_library_ready,
            "api_key_configured": gemini_key_ready,
            "live": gemini_live_check,
        },
        "openai": {
            "ready": openai_ready,
            "library": openai_library_ready,
            "api_key_configured": openai_key_ready,
            "base_url": openai_base_url or None,
            "model": os.getenv("OPENAI_VISION_MODEL", "gpt-4.1-mini"),
            "live": openai_live_check,
        },
        "frame_extraction_config": {
            "ready": True,
            "fps": FRAME_EXTRACTION["fps"],
            "min_blur_threshold": FRAME_EXTRACTION["min_blur_threshold"],
            "jpeg_quality": FRAME_EXTRACTION["jpeg_quality"],
        },
    }

    missing_required = [
        name for name, ready in capabilities.items()
        if not ready
    ]

    if required_ready:
        status = "ready"
    elif degraded:
        status = "degraded"
    else:
        status = "not_ready"

    warnings = []
    if gemini_ready and not live_gemini:
        warnings.append(
            "Gemini is configured but not live-verified; run with live_gemini=true or --live-gemini to check quota/billing."
        )
    if openai_ready and not live_openai:
        warnings.append(
            "OpenAI vision fallback is configured but not live-verified; run with --live-openai to check key/quota."
        )
    if odometer_ready and not ocr_ready and (gemini_ready or openai_ready) and not live_gemini:
        warnings.append(
            "Odometer reading is relying on VLM fallback because no local OCR engine is available."
        )

    return {
        "status": status,
        "capabilities": capabilities,
        "checks": checks,
        "missing_required": missing_required,
        "warnings": warnings,
    }


def _check_gemini_live(*, enabled: bool, timeout_seconds: int) -> Dict[str, Any]:
    if not enabled:
        return {
            "ready": False,
            "reason": "Gemini library or GEMINI_API_KEY is not configured",
        }

    try:
        import google.generativeai as genai

        genai.configure(api_key=os.getenv("GEMINI_API_KEY", "").strip())
        model = genai.GenerativeModel("gemini-2.5-pro")
        executor = ThreadPoolExecutor(max_workers=1)
        try:
            future = executor.submit(model.generate_content, "Return the word ready.")
            response = future.result(timeout=timeout_seconds)
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
        return {
            "ready": bool(getattr(response, "text", None)),
            "reason": None,
        }
    except FutureTimeoutError:
        return {
            "ready": False,
            "reason": f"Gemini API timed out after {timeout_seconds} seconds",
        }
    except Exception as exc:
        return {
            "ready": False,
            "reason": f"Gemini API unavailable: {exc}",
        }


def _check_openai_live(*, enabled: bool, timeout_seconds: int) -> Dict[str, Any]:
    if not enabled:
        return {
            "ready": False,
            "reason": "OpenAI library and OPENAI_API_KEY/OPENAI_BASE_URL are not configured",
        }

    try:
        from openai import OpenAI

        base_url = _openai_base_url()
        client_kwargs = {
            "api_key": os.getenv("OPENAI_API_KEY", "").strip() or "local-openai-compatible",
        }
        if base_url:
            client_kwargs["base_url"] = base_url
        client = OpenAI(**client_kwargs)
        model = os.getenv("OPENAI_TEXT_MODEL", os.getenv("OPENAI_VISION_MODEL", "gpt-4.1-mini")).strip() or "gpt-4.1-mini"
        try:
            response = _call_openai_responses_ready(client, model, timeout_seconds)
            ready = bool(getattr(response, "output_text", None) or getattr(response, "output", None))
        except Exception:
            response = _call_openai_chat_ready(client, model, timeout_seconds)
            choices = getattr(response, "choices", None)
            ready = bool(choices)
        return {
            "ready": ready,
            "reason": None,
            "model": model,
        }
    except FutureTimeoutError:
        return {
            "ready": False,
            "reason": f"OpenAI API timed out after {timeout_seconds} seconds",
        }
    except Exception as exc:
        return {
            "ready": False,
            "reason": f"OpenAI API unavailable: {exc}",
        }


def _call_openai_responses_ready(client: Any, model: str, timeout_seconds: int) -> Any:
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(
            client.responses.create,
            model=model,
            input=[{"role": "user", "content": [{"type": "input_text", "text": "Return the word ready."}]}],
        )
        return future.result(timeout=timeout_seconds)
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def _call_openai_chat_ready(client: Any, model: str, timeout_seconds: int) -> Any:
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(
            client.chat.completions.create,
            model=model,
            messages=[{"role": "user", "content": "Return the word ready."}],
        )
        return future.result(timeout=timeout_seconds)
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
