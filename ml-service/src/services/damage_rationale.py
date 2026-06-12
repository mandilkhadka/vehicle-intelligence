"""
Per-detection rationale via Gemini.

After the local damage detector emits its locations, we batch the top N
highest-confidence snapshots (with their inferred panel labels) into a single
Gemini call and ask for a one-sentence rationale per location. The rationale
explains why this is likely real damage in plain English — far more useful
than a numeric confidence.

Failure is silent: if Gemini is unavailable, times out, returns malformed
JSON, or the GeminiAnalyzer wasn't initialized, locations simply keep
rationale = None and the rest of the pipeline continues.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


_MAX_BATCH = int(os.getenv("ML_DAMAGE_RATIONALE_MAX", "8"))
_TIMEOUT_SECONDS = float(os.getenv("ML_DAMAGE_RATIONALE_TIMEOUT", "45"))
_MIN_CONFIDENCE = float(os.getenv("ML_DAMAGE_RATIONALE_MIN_CONFIDENCE", "0.45"))

_JSON_BLOCK_RE = re.compile(r"\{[\s\S]*\}")


def _has_vlm_provider(analyzer: Any) -> bool:
    """True if the analyzer has any VLM provider wired (Ollama, Gemini, or OpenAI)."""
    if analyzer is None:
        return False
    ollama = getattr(analyzer, "ollama", None)
    if ollama is not None and getattr(ollama, "available", False):
        return True
    if getattr(analyzer, "model", None) and getattr(analyzer, "api_key", None):
        return True
    if getattr(analyzer, "openai_client", None) and getattr(analyzer, "openai_api_key", None):
        return True
    return False


def _uploads_root(backend_root: str) -> str:
    """Shared uploads dir; mirrors get_uploads_root() in src/api/process.py
    (UPLOADS_ROOT env first — set in Docker — then the local checkout layout)."""
    configured = os.getenv("UPLOADS_ROOT", "").strip()
    if configured:
        return os.path.abspath(configured)
    return os.path.abspath(os.path.join(backend_root, "backend", "uploads"))


def _resolve_snapshot_path(snapshot: Optional[str], backend_root: str) -> Optional[str]:
    """Snapshots are stored as relative paths under the uploads root (e.g.
    'frames/<id>/damage_snapshots/scratch_001.jpg'). Promote to absolute."""
    if not snapshot:
        return None
    if os.path.isabs(snapshot):
        return snapshot if os.path.exists(snapshot) else None
    candidate = os.path.join(_uploads_root(backend_root), snapshot)
    return candidate if os.path.exists(candidate) else None


def _select_candidates(locations: List[Dict[str, Any]]) -> List[int]:
    """Indices of the top-N highest-confidence locations that have a snapshot."""
    scored = []
    for idx, loc in enumerate(locations):
        if not isinstance(loc, dict):
            continue
        if not loc.get("snapshot"):
            continue
        conf = float(loc.get("confidence") or 0.0)
        if conf < _MIN_CONFIDENCE:
            continue
        scored.append((conf, idx))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [idx for _, idx in scored[:_MAX_BATCH]]


def _build_prompt(items: List[Dict[str, Any]]) -> str:
    bullets = "\n".join(
        f"- index={i}: type={it.get('type','unknown')}, "
        f"part={it.get('part_label') or it.get('part') or 'unknown area'}, "
        f"severity={it.get('severity','medium')}, "
        f"confidence={round(float(it.get('confidence') or 0.0), 2)}"
        for i, it in enumerate(items)
    )
    return (
        "You are a vehicle damage inspector. I will give you cropped images of "
        "potential damage detected by a local computer-vision model. For each "
        "image, write ONE short sentence explaining what is visible and whether "
        "it looks like real damage of the stated type. Keep each rationale under "
        "25 words. Be specific and grounded in the image — do not invent "
        "details. If the image clearly does NOT show the claimed damage type, "
        "say so and suggest what it might actually be.\n\n"
        "Stated context per image (matches the image order I send):\n"
        f"{bullets}\n\n"
        "Return ONLY a JSON object with this exact shape, no markdown:\n"
        "{\n"
        '  "rationales": [\n'
        '    {"index": 0, "rationale": "...", "likely_real": true},\n'
        "    ...\n"
        "  ]\n"
        "}"
    )


def _parse_response(text: str, count: int) -> Dict[int, Dict[str, Any]]:
    if not text:
        return {}
    match = _JSON_BLOCK_RE.search(text)
    if not match:
        return {}
    try:
        data = json.loads(match.group(0))
    except Exception:
        return {}
    rationales = data.get("rationales") if isinstance(data, dict) else None
    if not isinstance(rationales, list):
        return {}
    out: Dict[int, Dict[str, Any]] = {}
    for item in rationales:
        if not isinstance(item, dict):
            continue
        idx = item.get("index")
        try:
            idx_i = int(idx)
        except (TypeError, ValueError):
            continue
        if idx_i < 0 or idx_i >= count:
            continue
        rationale = item.get("rationale")
        if not isinstance(rationale, str):
            continue
        out[idx_i] = {
            "rationale": rationale.strip()[:280],
            "likely_real": bool(item.get("likely_real", True)),
        }
    return out


async def attach_rationales(
    damage_data: Dict[str, Any],
    gemini_analyzer: Any,
    *,
    backend_root: str,
) -> None:
    """
    Mutate damage_data in-place so the highest-confidence locations gain:
        rationale: str | None
        rationale_likely_real: bool | None
    Silent on any failure path.
    """
    if not isinstance(damage_data, dict):
        return
    locations = damage_data.get("locations") or []
    if not locations:
        return

    # Initialize fields so the schema is consistent regardless of outcome.
    for loc in locations:
        if isinstance(loc, dict):
            loc.setdefault("rationale", None)
            loc.setdefault("rationale_likely_real", None)

    if not _has_vlm_provider(gemini_analyzer):
        damage_data.setdefault("rationale_available", False)
        return

    candidate_indices = _select_candidates(locations)
    if not candidate_indices:
        damage_data["rationale_available"] = True
        damage_data.setdefault("rationale_count", 0)
        return

    image_paths: List[str] = []
    items: List[Dict[str, Any]] = []
    used_indices: List[int] = []
    for idx in candidate_indices:
        loc = locations[idx]
        abs_path = _resolve_snapshot_path(loc.get("snapshot"), backend_root)
        if not abs_path:
            continue
        image_paths.append(abs_path)
        items.append(loc)
        used_indices.append(idx)

    if not image_paths:
        damage_data["rationale_available"] = True
        damage_data.setdefault("rationale_count", 0)
        return

    prompt = _build_prompt(items)

    def _invoke() -> Optional[str]:
        # Routes through whichever VLM provider is configured (Ollama, Gemini,
        # or OpenAI). Image order matches the prompt's stated context order.
        try:
            return gemini_analyzer.vlm_generate_text(prompt, image_paths)  # type: ignore[attr-defined]
        except Exception as exc:
            logger.warning("Damage rationale VLM call failed: %s", exc)
            return None

    try:
        text = await asyncio.wait_for(asyncio.to_thread(_invoke), timeout=_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        logger.warning("Damage rationale generation timed out after %ss", _TIMEOUT_SECONDS)
        damage_data["rationale_available"] = False
        damage_data.setdefault("rationale_count", 0)
        return
    except Exception as exc:
        logger.warning("Damage rationale generation failed: %s", exc)
        damage_data["rationale_available"] = False
        damage_data.setdefault("rationale_count", 0)
        return

    parsed = _parse_response(text or "", len(items))
    attached = 0
    for local_idx, loc_idx in enumerate(used_indices):
        result = parsed.get(local_idx)
        if not result:
            continue
        loc = locations[loc_idx]
        if isinstance(loc, dict):
            loc["rationale"] = result["rationale"]
            loc["rationale_likely_real"] = result["likely_real"]
            attached += 1

    damage_data["rationale_available"] = True
    damage_data["rationale_count"] = attached
