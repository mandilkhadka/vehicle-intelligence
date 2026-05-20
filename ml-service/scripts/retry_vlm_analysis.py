"""
Retry VLM analysis from a saved ML /api/process response or backend inspection.

This lets operators rerun only the Gemini/OpenAI visual analysis step after a
quota, billing, or key issue is fixed, using the organized frame package already
produced by the video pipeline.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import mimetypes
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Tuple

SRC_PARENT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SRC_PARENT))

from src.services.gemini_analyzer import GeminiAnalyzer  # noqa: E402


PATH_KEYS = ("frame", "organized_path", "crop_path", "readout_crop_path")
IDENTITY_OVERRIDE_FIELDS = (
    "brand",
    "model",
    "year",
    "variant",
    "type",
    "vehicle_category",
    "category",
    "color",
    "vin",
    "registration",
)


def normalize_process_response(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize saved API or DB inspection JSON into process-response shape."""
    normalized = deepcopy(payload)
    report = _json_dict(normalized.get("inspection_report"))
    if report is None and isinstance(normalized.get("report"), dict):
        report = deepcopy(normalized.get("report"))
    if report is not None:
        normalized["report"] = report

    vehicle_info = _json_dict(normalized.get("vehicle_info"))
    if vehicle_info is not None:
        normalized["vehicle_info"] = vehicle_info
    elif not isinstance(normalized.get("vehicle_info"), dict) and isinstance(report, dict):
        vehicle_details = report.get("vehicle_details")
        if isinstance(vehicle_details, dict):
            normalized["vehicle_info"] = deepcopy(vehicle_details)

    if not isinstance(normalized.get("frame_analysis"), dict) and isinstance(report, dict):
        frame_analysis = report.get("frame_analysis")
        if isinstance(frame_analysis, dict):
            normalized["frame_analysis"] = deepcopy(frame_analysis)

    if not isinstance(normalized.get("gemini_analysis"), dict) and isinstance(report, dict):
        gemini_analysis = report.get("gemini_analysis")
        if isinstance(gemini_analysis, dict):
            normalized["gemini_analysis"] = deepcopy(gemini_analysis)

    return normalized


def prepare_vlm_retry_inputs(
    process_response: Dict[str, Any],
    *,
    uploads_root: Path,
) -> Tuple[List[str], Dict[str, Any]]:
    """Return absolute representative frame paths and absolutized frame_analysis."""
    frame_analysis = deepcopy(process_response.get("frame_analysis") or {})
    _absolutize_frame_analysis(frame_analysis, uploads_root=uploads_root)

    frames: List[str] = []
    for payload in frame_analysis.get("representative_frames") or []:
        if not isinstance(payload, dict):
            continue
        path = payload.get("frame") or payload.get("organized_path")
        if path and Path(str(path)).exists() and str(path) not in frames:
            frames.append(str(path))

    if not frames:
        angle_shots = frame_analysis.get("angle_shots") if isinstance(frame_analysis.get("angle_shots"), dict) else {}
        for payload in angle_shots.values():
            if not isinstance(payload, dict):
                continue
            path = payload.get("organized_path") or payload.get("frame")
            if path and Path(str(path)).exists() and str(path) not in frames:
                frames.append(str(path))

    return frames, frame_analysis


def merge_vlm_retry_result(
    process_response: Dict[str, Any],
    vlm_result: Dict[str, Any],
) -> Dict[str, Any]:
    """Return a process response copy with the fresh VLM result merged in."""
    merged = deepcopy(process_response)
    result = deepcopy(vlm_result)
    merged["gemini_analysis"] = result

    vehicle_info = _merge_vehicle_info(merged.get("vehicle_info") or {}, result)
    merged["vehicle_info"] = vehicle_info

    report = merged.get("report")
    if not isinstance(report, dict):
        report = {}
    else:
        report = deepcopy(report)
    report["gemini_analysis"] = result
    report["visual_analysis"] = {
        "available": bool(result.get("available")),
        "reason": result.get("reason"),
        "provider": result.get("provider"),
    }
    report["vehicle_details"] = {
        **(report.get("vehicle_details") if isinstance(report.get("vehicle_details"), dict) else {}),
        **vehicle_info,
    }
    report.pop("pipeline_audit", None)
    merged["report"] = report
    return merged


def merge_identity_override(
    process_response: Dict[str, Any],
    identity_override: Dict[str, Any] | None,
) -> Dict[str, Any]:
    """Return a process response copy with trusted vehicle identity evidence merged in."""
    if not isinstance(identity_override, dict) or not identity_override:
        return deepcopy(process_response)

    merged = deepcopy(process_response)
    vehicle_info = _merge_vehicle_identity_override(
        merged.get("vehicle_info") if isinstance(merged.get("vehicle_info"), dict) else {},
        identity_override,
    )
    merged["vehicle_info"] = vehicle_info

    report = merged.get("report")
    if not isinstance(report, dict):
        report = {}
    else:
        report = deepcopy(report)
    report["vehicle_details"] = {
        **(report.get("vehicle_details") if isinstance(report.get("vehicle_details"), dict) else {}),
        **vehicle_info,
    }
    report.pop("pipeline_audit", None)
    merged["report"] = report
    return merged


def validate_vlm_result_import(vlm_result: Dict[str, Any]) -> Tuple[bool, str | None]:
    """Return whether an externally supplied VLM result is safe to merge."""
    if not isinstance(vlm_result, dict):
        return False, "VLM result must be a JSON object."
    if not isinstance(vlm_result.get("available"), bool):
        return False, "VLM result must include boolean field 'available'."
    if vlm_result.get("available") and not isinstance(vlm_result.get("vehicle"), dict):
        return False, "Available VLM result must include a vehicle object."
    return True, None


def build_external_vlm_request(
    process_response: Dict[str, Any],
    *,
    uploads_root: Path,
    include_image_data: bool = False,
) -> Dict[str, Any]:
    """Return a portable prompt + frame package for an external VLM review."""
    frames, frame_analysis = prepare_vlm_retry_inputs(
        process_response,
        uploads_root=uploads_root,
    )
    if not frames:
        raise ValueError("No existing representative frames found for VLM request export.")

    selected = GeminiAnalyzer._select_frames(frames, 12, frame_analysis)
    if not selected:
        raise ValueError("No selected frames available for VLM request export.")

    prompt = GeminiAnalyzer._build_prompt(selected)
    return {
        "prompt": prompt,
        "frames": [
            _external_frame_payload(index, item, include_image_data=include_image_data)
            for index, item in enumerate(selected, start=1)
        ],
        "frame_analysis": frame_analysis,
        "expected_response_schema": {
            "available": True,
            "provider": "external_vlm_review",
            "vehicle": {
                "brand": "string",
                "model": "string",
                "year": "string",
                "variant": "string",
                "type": "string",
                "vehicle_category": "string",
                "color": "string",
                "confidence": 0.0,
            },
            "overall_condition": "string",
            "damage_items": [
                {
                    "type": "scratch|dent|rust|crack|paint_damage|other",
                    "location": "string",
                    "severity": "low|medium|high",
                    "confidence": 0.0,
                    "notes": "string",
                }
            ],
            "modification_items": [
                {
                    "part": "wheels|lights|body|exhaust|paint_or_wrap|interior|other",
                    "status": "stock|modified|unknown",
                    "confidence": 0.0,
                    "notes": "string",
                }
            ],
            "summary": "string",
        },
    }


def _merge_vehicle_info(base_info: Dict[str, Any], vlm_result: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(vlm_result, dict) or not vlm_result.get("available"):
        return deepcopy(base_info or {})

    vehicle = vlm_result.get("vehicle") if isinstance(vlm_result.get("vehicle"), dict) else {}
    merged = deepcopy(base_info or {})
    for key in (
        "type",
        "brand",
        "model",
        "year",
        "variant",
        "vehicle_category",
        "category",
        "color",
        "generation",
    ):
        value = vehicle.get(key)
        if value is None:
            continue
        if isinstance(value, str) and value.strip().lower() in {"", "unknown", "null", "none"}:
            continue
        merged[key] = value

    try:
        vlm_confidence = float(vehicle.get("confidence"))
    except (TypeError, ValueError):
        vlm_confidence = 0.0
    try:
        base_confidence = float(merged.get("confidence") or 0.0)
    except (TypeError, ValueError):
        base_confidence = 0.0
    merged["confidence"] = max(base_confidence, vlm_confidence)
    return merged


def _external_frame_payload(
    index: int,
    item: Dict[str, Any],
    *,
    include_image_data: bool,
) -> Dict[str, Any]:
    path = Path(str(item.get("frame") or ""))
    payload = {
        "index": index,
        "path": str(path),
        "view": item.get("view"),
        "timestamp_seconds": item.get("timestamp_seconds"),
        "quality_score": item.get("quality_score"),
        "vehicle_ratio": item.get("vehicle_ratio"),
        "high_confidence": item.get("high_confidence"),
        "semantic_source": item.get("semantic_source"),
    }
    if include_image_data:
        mime_type = mimetypes.guess_type(path.name)[0] or "image/jpeg"
        image_data = base64.b64encode(path.read_bytes()).decode("ascii")
        payload["data_url"] = f"data:{mime_type};base64,{image_data}"
    return {key: value for key, value in payload.items() if value is not None}


def _merge_vehicle_identity_override(
    base_info: Dict[str, Any],
    override: Dict[str, Any] | None,
) -> Dict[str, Any]:
    if not isinstance(override, dict) or not override:
        return deepcopy(base_info or {})

    merged = deepcopy(base_info or {})
    applied: List[str] = []
    for field in IDENTITY_OVERRIDE_FIELDS:
        value = override.get(field)
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        merged[field] = value
        applied.append(field)

    source = str(override.get("source") or "provided_identity_evidence").strip()
    merged["identity_source"] = source
    if applied:
        merged["identity_override_fields"] = applied
        merged["identity_notes"] = (
            f"Exact identity fields merged from {source}; video-derived fields remain candidates where not overridden."
        )

    try:
        override_confidence = float(override.get("confidence"))
    except (TypeError, ValueError):
        override_confidence = 0.95 if applied else 0.0
    try:
        base_confidence = float(merged.get("confidence") or 0.0)
    except (TypeError, ValueError):
        base_confidence = 0.0
    merged["confidence"] = max(base_confidence, override_confidence)
    return merged


def _absolutize_frame_analysis(frame_analysis: Dict[str, Any], *, uploads_root: Path) -> None:
    def absolutize_payload(payload: Dict[str, Any]) -> None:
        for key in PATH_KEYS:
            value = payload.get(key)
            if not value:
                continue
            path = Path(str(value))
            if not path.is_absolute():
                payload[key] = str(uploads_root / path)

    angle_shots = frame_analysis.get("angle_shots") if isinstance(frame_analysis.get("angle_shots"), dict) else {}
    for payload in angle_shots.values():
        if isinstance(payload, dict):
            absolutize_payload(payload)

    for collection_key in ("dashboard_candidates", "representative_frames"):
        for payload in frame_analysis.get(collection_key) or []:
            if isinstance(payload, dict):
                absolutize_payload(payload)


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _json_dict(value: Any) -> Dict[str, Any] | None:
    if isinstance(value, dict):
        return deepcopy(value)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--inspection-json",
        required=True,
        help="Saved ML /api/process response JSON or backend inspection record JSON",
    )
    parser.add_argument(
        "--uploads-root",
        default=str(SRC_PARENT.parent / "backend" / "uploads"),
        help="Backend uploads directory used to resolve relative frame paths",
    )
    parser.add_argument("--output-json", help="Optional file to write VLM analysis JSON")
    parser.add_argument(
        "--merged-output-json",
        help="Optional file to write a saved process response with the fresh VLM result merged in",
    )
    parser.add_argument(
        "--vlm-result-json",
        help="Optional precomputed Gemini/OpenAI-compatible VLM result JSON to merge without calling a provider",
    )
    parser.add_argument(
        "--export-request-json",
        help=(
            "Optional file to write the selected frame paths, metadata, prompt, "
            "and response schema for an external VLM review"
        ),
    )
    parser.add_argument(
        "--include-image-data",
        action="store_true",
        help="Embed selected frames as base64 data URLs in --export-request-json",
    )
    parser.add_argument(
        "--identity-override-json",
        help=(
            "Optional trusted identity JSON to merge, including fields like "
            "brand, model, year, variant, type, category, VIN, or registration"
        ),
    )
    parser.add_argument(
        "--skip-vlm",
        action="store_true",
        help=(
            "Do not call Gemini/OpenAI; normalize the saved inspection and merge "
            "--identity-override-json and/or --vlm-result-json into --merged-output-json"
        ),
    )
    return parser.parse_args()


async def main_async() -> int:
    args = parse_args()
    response = normalize_process_response(_load_json(Path(args.inspection_json)))
    identity_override = (
        _load_json(Path(args.identity_override_json))
        if args.identity_override_json
        else None
    )
    vlm_result = _load_json(Path(args.vlm_result_json)) if args.vlm_result_json else None
    if vlm_result is not None:
        valid, reason = validate_vlm_result_import(vlm_result)
        if not valid:
            print(reason, file=sys.stderr)
            return 2

    if args.export_request_json:
        try:
            request_package = build_external_vlm_request(
                response,
                uploads_root=Path(args.uploads_root),
                include_image_data=args.include_image_data,
            )
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        Path(args.export_request_json).write_text(
            json.dumps(request_package, indent=2) + "\n",
            encoding="utf-8",
        )
        if not any(
            [
                args.output_json,
                args.merged_output_json,
                args.vlm_result_json,
                args.identity_override_json,
                args.skip_vlm,
            ]
        ):
            return 0
        if args.skip_vlm and not identity_override and vlm_result is None:
            return 0

    if args.skip_vlm or vlm_result is not None:
        if not args.merged_output_json:
            print("--skip-vlm/--vlm-result-json requires --merged-output-json.", file=sys.stderr)
            return 2
        if not identity_override and vlm_result is None:
            print("--skip-vlm requires --identity-override-json or --vlm-result-json.", file=sys.stderr)
            return 2
        merged = response
        if vlm_result is not None:
            merged = merge_vlm_retry_result(merged, vlm_result)
            if args.output_json:
                Path(args.output_json).write_text(json.dumps(vlm_result, indent=2) + "\n", encoding="utf-8")
        if identity_override:
            merged = merge_identity_override(merged, identity_override)
        Path(args.merged_output_json).write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
        return 0 if vlm_result is None or vlm_result.get("available") else 2

    frames, frame_analysis = prepare_vlm_retry_inputs(
        response,
        uploads_root=Path(args.uploads_root),
    )
    if not frames:
        print("No existing representative frames found for VLM retry.", file=sys.stderr)
        return 2

    analyzer = GeminiAnalyzer()
    result = await analyzer.analyze(frames, frame_analysis)
    output = json.dumps(result, indent=2)
    if args.output_json:
        Path(args.output_json).write_text(output + "\n", encoding="utf-8")
    else:
        print(output)

    if args.merged_output_json:
        merged = merge_vlm_retry_result(response, result)
        if identity_override:
            merged = merge_identity_override(merged, identity_override)
        Path(args.merged_output_json).write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")

    return 0 if result.get("available") else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))
