"""
Check whether the local ML service environment can run the full inspection pipeline.

By default this avoids loading large models or calling paid APIs. Pass
--live-gemini, --live-openai, or --live-ollama to verify configured VLM
providers with a small request (--live-ollama confirms the server is up and the
configured models are pulled).
"""

import argparse
import json
import sys
from pathlib import Path

SRC_PARENT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SRC_PARENT))

from src.config.env import load_ml_environment  # noqa: E402
from src.services.pipeline_readiness import build_pipeline_readiness  # noqa: E402


def _load_env_files() -> None:
    load_ml_environment()


def main() -> int:
    _load_env_files()

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live-gemini",
        action="store_true",
        help="Call Gemini once to verify API key/quota instead of only checking configuration.",
    )
    parser.add_argument(
        "--gemini-timeout-seconds",
        type=int,
        default=10,
        help="Timeout for --live-gemini.",
    )
    parser.add_argument(
        "--live-openai",
        action="store_true",
        help="Call OpenAI once to verify API key/quota instead of only checking configuration.",
    )
    parser.add_argument(
        "--openai-timeout-seconds",
        type=int,
        default=10,
        help="Timeout for --live-openai.",
    )
    parser.add_argument(
        "--live-ollama",
        action="store_true",
        help="Query the Ollama server once to verify it is up and the configured models are pulled.",
    )
    parser.add_argument(
        "--ollama-timeout-seconds",
        type=int,
        default=10,
        help="Timeout for --live-ollama.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON only.",
    )
    args = parser.parse_args()

    readiness = build_pipeline_readiness(
        live_gemini=args.live_gemini,
        live_openai=args.live_openai,
        live_ollama=args.live_ollama,
        gemini_timeout_seconds=args.gemini_timeout_seconds,
        openai_timeout_seconds=args.openai_timeout_seconds,
        ollama_timeout_seconds=args.ollama_timeout_seconds,
    )

    if args.json:
        print(json.dumps(readiness, indent=2))
    else:
        _print_summary(readiness)

    return 0 if readiness["status"] == "ready" else 2


def _print_summary(readiness):
    print("Vehicle inspection pipeline readiness")
    print(f"Status: {readiness['status']}")
    if readiness["missing_required"]:
        print("Missing required capabilities:")
        for name in readiness["missing_required"]:
            print(f"- {name}")
    else:
        print("All required capabilities are available.")

    if readiness.get("warnings"):
        print("\nWarnings:")
        for warning in readiness["warnings"]:
            print(f"- {warning}")

    print("\nCapabilities:")
    for name, ready in readiness["capabilities"].items():
        marker = "ok" if ready else "missing"
        print(f"- {name}: {marker}")

    gemini_live = (readiness["checks"].get("gemini") or {}).get("live")
    if gemini_live and not gemini_live.get("ready"):
        print(f"\nGemini live check: {gemini_live.get('reason')}")

    openai_live = (readiness["checks"].get("openai") or {}).get("live")
    if openai_live and not openai_live.get("ready"):
        print(f"\nOpenAI live check: {openai_live.get('reason')}")

    ollama_live = (readiness["checks"].get("ollama") or {}).get("live")
    if ollama_live and ollama_live.get("reason"):
        print(f"\nOllama live check: {ollama_live.get('reason')}")

    ocr = readiness["checks"].get("ocr") or {}
    if not ocr.get("ready"):
        print(
            "\nOdometer OCR needs PaddleOCR, or pytesseract plus the tesseract "
            "system binary. Gemini can be used as a fallback when configured."
        )


if __name__ == "__main__":
    raise SystemExit(main())
