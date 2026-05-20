"""
Evaluate the video-understanding stage on a walkaround video.

This script runs frame extraction and frame organization without requiring the
backend/frontend services. It writes a JSON manifest with selected angle shots,
dashboard candidates, coverage, and VLM representative frames.

Usage:
    python scripts/evaluate_video_understanding.py /path/to/video.mov --output-dir /tmp/vip-eval
    python scripts/evaluate_video_understanding.py /path/to/video.mov --with-models
    python scripts/evaluate_video_understanding.py /path/to/video.mov --expected-json annotations.json
    python scripts/evaluate_video_understanding.py /path/to/video.mov --expected-json annotations.json --inspection-json process_response.json
"""

import argparse
import asyncio
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

SRC_PARENT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SRC_PARENT))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from src.config.constants import FRAME_EXTRACTION  # noqa: E402
from src.services.frame_extractor import FrameExtractor  # noqa: E402
from src.services.frame_organizer import EXTERIOR_VIEWS, VehicleFrameOrganizer  # noqa: E402
from src.services.model_registry import ModelRegistry  # noqa: E402
from src.services.odometer_reader import OdometerReader  # noqa: E402

logger = logging.getLogger("evaluate_video_understanding")


async def run(args: argparse.Namespace) -> int:
    video_path = Path(args.video).resolve()
    if not video_path.exists():
        raise FileNotFoundError(video_path)

    output_dir = Path(args.output_dir).resolve() if args.output_dir else _default_output_dir(video_path)
    frames_dir = output_dir / "frames"
    output_dir.mkdir(parents=True, exist_ok=True)
    frames_dir.mkdir(parents=True, exist_ok=True)

    yolo_model = None
    clip_model = None
    clip_processor = None
    model_setup_seconds = 0.0

    if args.with_models:
        t0 = time.time()
        registry = ModelRegistry()
        registry.initialize_all_models()
        yolo_model = registry.get_yolo_model()
        clip_model = registry.get_clip_model()
        clip_processor = registry.get_clip_processor()
        model_setup_seconds = time.time() - t0

    extractor = FrameExtractor(
        fps=args.fps,
        min_blur_threshold=args.blur_threshold,
        jpeg_quality=args.jpeg_quality,
    )
    organizer = VehicleFrameOrganizer(
        yolo_model=yolo_model,
        clip_model=clip_model,
        clip_processor=clip_processor,
    )

    t0 = time.time()
    frame_paths = await extractor.extract_frames(str(video_path), str(frames_dir))
    extraction_seconds = time.time() - t0
    frame_metadata = _load_frame_metadata(frames_dir)

    t0 = time.time()
    frame_analysis = await organizer.organize(frame_paths, "evaluation")
    organization_seconds = time.time() - t0
    expected = _load_expected(Path(args.expected_json)) if args.expected_json else {}
    inspection_payload = _load_inspection_payload(Path(args.inspection_json)) if args.inspection_json else None

    odometer_ocr = None
    if args.read_odometer or _expected_has_odometer(expected):
        t0 = time.time()
        odometer_ocr = await _read_odometer_from_frame_analysis(frame_analysis, expected)
        odometer_ocr["seconds"] = round(time.time() - t0, 3)

    manifest = _build_manifest(
        video_path=video_path,
        output_dir=output_dir,
        frame_paths=frame_paths,
        frame_metadata=frame_metadata,
        frame_analysis=frame_analysis,
        odometer_ocr=odometer_ocr,
        args=args,
        timings={
            "model_setup_seconds": round(model_setup_seconds, 3),
            "frame_extraction_seconds": round(extraction_seconds, 3),
            "frame_organization_seconds": round(organization_seconds, 3),
        },
    )
    if inspection_payload:
        manifest["inspection"] = _compact_inspection_payload(inspection_payload)
    if expected:
        manifest["validation"] = _validate_against_expected(
            frame_analysis=frame_analysis,
            expected_path=Path(args.expected_json),
            expected=expected,
            odometer_ocr=odometer_ocr,
            inspection_payload=inspection_payload,
        )

    manifest_path = output_dir / args.manifest_name
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    if args.write_annotation_artifacts:
        contact_sheet_path = output_dir / args.contact_sheet_name
        annotation_template_path = output_dir / args.annotation_template_name
        _write_contact_sheet(
            frame_paths=frame_paths,
            manifest=manifest,
            output_path=contact_sheet_path,
            thumb_width=args.contact_sheet_thumb_width,
            columns=args.contact_sheet_columns,
        )
        _write_annotation_template(
            frame_paths=frame_paths,
            manifest=manifest,
            output_path=annotation_template_path,
        )
        manifest["artifacts"] = {
            "contact_sheet": str(contact_sheet_path),
            "annotation_template": str(annotation_template_path),
        }
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    _print_summary(manifest, manifest_path)
    return _exit_code(manifest, args)


def _build_manifest(
    video_path: Path,
    output_dir: Path,
    frame_paths: list[str],
    frame_metadata: Dict[str, Any],
    frame_analysis: Dict[str, Any],
    odometer_ocr: Dict[str, Any] | None,
    args: argparse.Namespace,
    timings: Dict[str, float],
) -> Dict[str, Any]:
    coverage = frame_analysis.get("coverage") or {}
    angle_shots = frame_analysis.get("angle_shots") or {}
    dashboard_candidates = frame_analysis.get("dashboard_candidates") or []
    representative_frames = frame_analysis.get("representative_frames") or []
    extraction_metadata = frame_analysis.get("extraction_metadata") or {}

    return {
        "video": str(video_path),
        "output_dir": str(output_dir),
        "configuration": {
            "fps": args.fps,
            "blur_threshold": args.blur_threshold,
            "jpeg_quality": args.jpeg_quality,
            "with_models": args.with_models,
            "min_coverage": args.min_coverage,
            "min_high_confidence_coverage": args.min_high_confidence_coverage,
            "min_dashboard_candidates": args.min_dashboard_candidates,
            "read_odometer": args.read_odometer,
            "min_odometer_confidence": args.min_odometer_confidence,
        },
        "timings": timings,
        "summary": {
            "frames_extracted": len(frame_paths),
            "frames_analyzed": frame_analysis.get("frames_analyzed", 0),
            "frames_total": frame_analysis.get("frames_total", 0),
            "organizer_method": frame_analysis.get("method"),
            "coverage_ratio": coverage.get("ratio", 0.0),
            "high_confidence_coverage_ratio": coverage.get("high_confidence_ratio", 0.0),
            "present_views": coverage.get("present_views", []),
            "high_confidence_views": coverage.get("high_confidence_views", []),
            "low_confidence_views": coverage.get("low_confidence_views", []),
            "missing_views": coverage.get("missing_views", []),
            "temporal_coverage_ratio": extraction_metadata.get("temporal_coverage_ratio"),
            "dashboard_candidates": len(dashboard_candidates),
            "representative_frames": len(representative_frames),
        },
        "frame_metadata": frame_metadata,
        "extraction_metadata": extraction_metadata,
        "odometer_ocr": odometer_ocr,
        "angle_shots": {
            view: _compact_item(angle_shots.get(view))
            for view in [*EXTERIOR_VIEWS, "interior", "dashboard", "odometer"]
            if angle_shots.get(view)
        },
        "dashboard_candidates": [_compact_item(item) for item in dashboard_candidates],
        "representative_frames": [_compact_item(item) for item in representative_frames],
    }


def _load_expected(expected_path: Path) -> Dict[str, Any]:
    expected_path = expected_path.resolve()
    return json.loads(expected_path.read_text(encoding="utf-8"))


def _load_inspection_payload(inspection_path: Path) -> Dict[str, Any]:
    inspection_path = inspection_path.resolve()
    return json.loads(inspection_path.read_text(encoding="utf-8"))


def _load_frame_metadata(frames_dir: Path) -> Dict[str, Any]:
    metadata_path = frames_dir / "frame_metadata.json"
    if not metadata_path.exists():
        return {}
    try:
        return json.loads(metadata_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        logger.warning("Could not parse frame metadata %s: %s", metadata_path, e)
        return {}


def _validate_against_expected(
    frame_analysis: Dict[str, Any],
    expected_path: Path,
    expected: Dict[str, Any],
    odometer_ocr: Dict[str, Any] | None = None,
    inspection_payload: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    expected_path = expected_path.resolve()
    angle_shots = frame_analysis.get("angle_shots") or {}
    dashboard_candidates = frame_analysis.get("dashboard_candidates") or []

    view_expectations = expected.get("views") or {}
    view_results = {}
    matched_views = 0
    total_views = 0
    for view, spec in view_expectations.items():
        total_views += 1
        selected = angle_shots.get(view) or {}
        matched = _selection_matches(selected, spec)
        if matched:
            matched_views += 1
        view_results[view] = {
            "selected_frame_index": selected.get("frame_index"),
            "selected_extracted_index": selected.get("extracted_index"),
            "selected_source_frame_index": selected.get("source_frame_index"),
            "selected_timestamp_seconds": selected.get("timestamp_seconds"),
            "expected": spec,
            "matched": matched,
            "selected_frame": selected.get("organized_path") or selected.get("frame"),
        }

    dashboard_spec = expected.get("dashboard")
    dashboard_matches = []
    if dashboard_spec is not None:
        for candidate in dashboard_candidates:
            dashboard_matches.append({
                "selected_frame_index": candidate.get("frame_index"),
                "selected_extracted_index": candidate.get("extracted_index"),
                "selected_source_frame_index": candidate.get("source_frame_index"),
                "selected_timestamp_seconds": candidate.get("timestamp_seconds"),
                "matched": _selection_matches(candidate, dashboard_spec),
                "selected_frame": (
                    candidate.get("readout_crop_path")
                    or candidate.get("crop_path")
                    or candidate.get("organized_path")
                    or candidate.get("frame")
                ),
            })

    dashboard_matched = any(item["matched"] for item in dashboard_matches) if dashboard_spec is not None else None
    view_accuracy = matched_views / total_views if total_views else None

    return {
        "expected_json": str(expected_path),
        "view_accuracy": round(view_accuracy, 4) if view_accuracy is not None else None,
        "matched_views": matched_views,
        "total_views": total_views,
        "views": view_results,
        "dashboard": {
            "expected": dashboard_spec,
            "matched": dashboard_matched,
            "candidates": dashboard_matches,
        } if dashboard_spec is not None else None,
        "odometer": _validate_odometer(odometer_ocr, expected.get("odometer")),
        "inspection": _validate_inspection(inspection_payload, expected),
    }


def _validate_inspection(
    inspection_payload: Dict[str, Any] | None,
    expected: Dict[str, Any],
) -> Dict[str, Any] | None:
    expected_spec = _expected_inspection_spec(expected)
    if not expected_spec:
        return None

    vehicle_expected = expected_spec.get("vehicle") or {}
    condition_expected = expected_spec.get("overall_condition")
    odometer_expected = expected_spec.get("odometer")
    visual_expected = expected_spec.get("visual_analysis")
    damage_expected = expected_spec.get("damage_items") or []
    modification_expected = expected_spec.get("modification_items") or []

    vehicle_actual = _extract_vehicle(inspection_payload)
    condition_actual = _extract_condition(inspection_payload)
    odometer_actual = _extract_odometer(inspection_payload)
    visual_actual = _extract_visual_analysis(inspection_payload)
    damage_actual = _extract_damage_items(inspection_payload)
    modification_actual = _extract_modification_items(inspection_payload)

    vehicle_validation = _validate_vehicle(vehicle_actual, vehicle_expected)
    condition_validation = _validate_scalar(condition_actual, condition_expected)
    odometer_validation = _validate_odometer(odometer_actual, odometer_expected)
    visual_validation = _validate_visual_analysis(visual_actual, visual_expected)
    damage_validation = _validate_item_list(
        actual_items=damage_actual,
        expected_items=damage_expected,
        fields=("type", "location", "severity"),
        aliases={"severity": {"medium": "moderate", "moderate": "medium"}},
    )
    modification_validation = _validate_item_list(
        actual_items=modification_actual,
        expected_items=modification_expected,
        fields=("part", "status"),
    )

    validations = [
        item for item in (
            vehicle_validation,
            condition_validation,
            odometer_validation,
            visual_validation,
            damage_validation,
            modification_validation,
        )
        if item is not None
    ]
    matched = all(item.get("matched") is not False for item in validations)
    return {
        "expected": expected_spec,
        "actual_available": inspection_payload is not None,
        "matched": matched,
        "vehicle": vehicle_validation,
        "overall_condition": condition_validation,
        "odometer": odometer_validation,
        "visual_analysis": visual_validation,
        "damage_items": damage_validation,
        "modification_items": modification_validation,
    }


def _expected_inspection_spec(expected: Dict[str, Any]) -> Dict[str, Any]:
    spec = expected.get("inspection") if isinstance(expected.get("inspection"), dict) else {}
    out: Dict[str, Any] = dict(spec)
    if "vehicle" in expected and "vehicle" not in out:
        out["vehicle"] = expected.get("vehicle")
    if "overall_condition" in expected and "overall_condition" not in out:
        out["overall_condition"] = expected.get("overall_condition")
    if "odometer" in expected and "odometer" not in out:
        out["odometer"] = expected.get("odometer")
    if "visual_analysis" in expected and "visual_analysis" not in out:
        out["visual_analysis"] = expected.get("visual_analysis")
    if "damage_items" in expected and "damage_items" not in out:
        out["damage_items"] = expected.get("damage_items")
    if "modification_items" in expected and "modification_items" not in out:
        out["modification_items"] = expected.get("modification_items")
    return {
        key: value for key, value in out.items()
        if value not in (None, "", [], {})
    }


def _validate_vehicle(actual: Dict[str, Any], expected: Dict[str, Any]) -> Dict[str, Any] | None:
    if not isinstance(expected, dict) or not expected:
        return None
    fields = ("brand", "model", "year", "variant", "type", "color")
    results = {}
    matched = 0
    total = 0
    for field in fields:
        expected_value = expected.get(field)
        if expected_value in (None, ""):
            continue
        total += 1
        actual_value = actual.get(field)
        field_matched = _text_matches(actual_value, expected_value)
        if field_matched:
            matched += 1
        results[field] = {
            "expected": expected_value,
            "actual": actual_value,
            "matched": field_matched,
        }
    if total == 0:
        return None
    return {
        "matched": matched == total,
        "matched_fields": matched,
        "total_fields": total,
        "fields": results,
    }


def _validate_scalar(actual: Any, expected: Any) -> Dict[str, Any] | None:
    if expected in (None, ""):
        return None
    matched = _text_matches(actual, expected)
    return {
        "expected": expected,
        "actual": actual,
        "matched": matched,
    }


def _validate_item_list(
    actual_items: List[Dict[str, Any]],
    expected_items: Any,
    fields: tuple[str, ...],
    aliases: Dict[str, Dict[str, str]] | None = None,
) -> Dict[str, Any] | None:
    if not isinstance(expected_items, list) or not expected_items:
        return None
    aliases = aliases or {}
    item_results = []
    matched_count = 0
    for expected in expected_items:
        if not isinstance(expected, dict):
            continue
        matched_item = _find_matching_item(actual_items, expected, fields, aliases)
        item_matched = matched_item is not None
        if item_matched:
            matched_count += 1
        item_results.append({
            "expected": expected,
            "matched": item_matched,
            "actual": matched_item,
        })
    total = len(item_results)
    if total == 0:
        return None
    return {
        "matched": matched_count == total,
        "matched_items": matched_count,
        "total_items": total,
        "items": item_results,
    }


def _find_matching_item(
    actual_items: List[Dict[str, Any]],
    expected: Dict[str, Any],
    fields: tuple[str, ...],
    aliases: Dict[str, Dict[str, str]],
) -> Dict[str, Any] | None:
    expected_fields = [
        field for field in fields
        if expected.get(field) not in (None, "")
    ]
    if not expected_fields:
        return None
    for actual in actual_items:
        if all(_text_matches(actual.get(field), expected.get(field), aliases.get(field)) for field in expected_fields):
            return actual
    return None


def _text_matches(actual: Any, expected: Any, aliases: Dict[str, str] | None = None) -> bool:
    actual_text = _normalize_text(actual)
    expected_text = _normalize_text(expected)
    if not expected_text:
        return True
    if not actual_text:
        return False
    if actual_text == expected_text or expected_text in actual_text or actual_text in expected_text:
        return True
    if aliases:
        actual_alias = aliases.get(actual_text)
        expected_alias = aliases.get(expected_text)
        return (
            actual_alias == expected_text
            or expected_alias == actual_text
            or (actual_alias is not None and expected_alias is not None and actual_alias == expected_alias)
        )
    return False


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().replace("_", " ").replace("-", " ").split())


def _extract_vehicle(payload: Dict[str, Any] | None) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    candidates = [
        payload.get("vehicle_info"),
        payload.get("vehicle"),
        (payload.get("gemini_analysis") or {}).get("vehicle") if isinstance(payload.get("gemini_analysis"), dict) else None,
        (payload.get("report") or {}).get("vehicle_details") if isinstance(payload.get("report"), dict) else None,
        ((payload.get("report") or {}).get("gemini_analysis") or {}).get("vehicle")
        if isinstance(payload.get("report"), dict) and isinstance((payload.get("report") or {}).get("gemini_analysis"), dict)
        else None,
    ]
    for candidate in candidates:
        if isinstance(candidate, dict) and candidate:
            return candidate
    return {}


def _extract_condition(payload: Dict[str, Any] | None) -> Any:
    if not isinstance(payload, dict):
        return None
    candidates = [
        (payload.get("gemini_analysis") or {}).get("overall_condition") if isinstance(payload.get("gemini_analysis"), dict) else None,
        payload.get("overall_condition"),
        (payload.get("report") or {}).get("overall_condition") if isinstance(payload.get("report"), dict) else None,
        ((payload.get("report") or {}).get("vehicle_details") or {}).get("condition")
        if isinstance(payload.get("report"), dict) and isinstance((payload.get("report") or {}).get("vehicle_details"), dict)
        else None,
        ((payload.get("report") or {}).get("gemini_analysis") or {}).get("overall_condition")
        if isinstance(payload.get("report"), dict) and isinstance((payload.get("report") or {}).get("gemini_analysis"), dict)
        else None,
    ]
    return next((item for item in candidates if item not in (None, "")), None)


def _extract_odometer(payload: Dict[str, Any] | None) -> Dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    candidates = [
        payload.get("odometer"),
        payload.get("odometer_info"),
        (payload.get("report") or {}).get("odometer_reading") if isinstance(payload.get("report"), dict) else None,
        ((payload.get("report") or {}).get("odometer") if isinstance(payload.get("report"), dict) else None),
    ]
    for candidate in candidates:
        if isinstance(candidate, dict) and candidate:
            if "value" in candidate:
                return candidate
            if "reading" in candidate:
                return {"value": candidate.get("reading"), **candidate}
        if isinstance(candidate, (int, float)):
            return {"value": candidate}
    if payload.get("odometer_value") is not None:
        return {
            "value": payload.get("odometer_value"),
            "confidence": payload.get("odometer_confidence"),
            "speedometer_image_path": payload.get("speedometer_image_path"),
        }
    return None


def _extract_visual_analysis(payload: Dict[str, Any] | None) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {
            "available": False,
            "reason": "inspection payload unavailable",
            "source": None,
        }

    candidates = [
        ("gemini_analysis", payload.get("gemini_analysis")),
        ("visual_analysis", payload.get("visual_analysis")),
        (
            "report.visual_analysis",
            (payload.get("report") or {}).get("visual_analysis")
            if isinstance(payload.get("report"), dict)
            else None,
        ),
        (
            "report.gemini_analysis",
            (payload.get("report") or {}).get("gemini_analysis")
            if isinstance(payload.get("report"), dict)
            else None,
        ),
    ]
    for source, candidate in candidates:
        if not isinstance(candidate, dict) or "available" not in candidate:
            continue
        return {
            "available": bool(candidate.get("available")),
            "reason": candidate.get("reason"),
            "source": source,
        }

    return {
        "available": False,
        "reason": "no visual analysis availability marker found",
        "source": None,
    }


def _validate_visual_analysis(actual: Dict[str, Any], expected: Any) -> Dict[str, Any] | None:
    if expected in (None, "", {}):
        return None

    if isinstance(expected, bool):
        expected_available = expected
    elif isinstance(expected, dict):
        if expected.get("available") is None:
            return None
        expected_available = bool(expected.get("available"))
    else:
        return None

    actual_available = bool((actual or {}).get("available"))
    return {
        "expected_available": expected_available,
        "actual_available": actual_available,
        "reason": (actual or {}).get("reason"),
        "source": (actual or {}).get("source"),
        "matched": actual_available is expected_available,
    }


def _extract_damage_items(payload: Dict[str, Any] | None) -> List[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    items = []
    gemini = payload.get("gemini_analysis") if isinstance(payload.get("gemini_analysis"), dict) else {}
    report = payload.get("report") if isinstance(payload.get("report"), dict) else {}
    report_gemini = report.get("gemini_analysis") if isinstance(report.get("gemini_analysis"), dict) else {}
    damage = payload.get("damage") if isinstance(payload.get("damage"), dict) else {}
    for source in (gemini.get("damage_items"), report_gemini.get("damage_items"), damage.get("locations")):
        if isinstance(source, list):
            items.extend(item for item in source if isinstance(item, dict))
    return items


def _extract_modification_items(payload: Dict[str, Any] | None) -> List[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    items = []
    gemini = payload.get("gemini_analysis") if isinstance(payload.get("gemini_analysis"), dict) else {}
    report = payload.get("report") if isinstance(payload.get("report"), dict) else {}
    report_gemini = report.get("gemini_analysis") if isinstance(report.get("gemini_analysis"), dict) else {}
    modification = report.get("modification_assessment") if isinstance(report.get("modification_assessment"), dict) else {}
    for source in (gemini.get("modification_items"), report_gemini.get("modification_items"), modification.get("items")):
        if isinstance(source, list):
            items.extend(item for item in source if isinstance(item, dict))
    return items


def _compact_inspection_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "vehicle": _extract_vehicle(payload),
        "overall_condition": _extract_condition(payload),
        "visual_analysis": _extract_visual_analysis(payload),
        "damage_items": _extract_damage_items(payload),
        "modification_items": _extract_modification_items(payload),
        "odometer": _extract_odometer(payload),
    }


async def _read_odometer_from_frame_analysis(
    frame_analysis: Dict[str, Any],
    expected: Dict[str, Any],
) -> Dict[str, Any]:
    paths = _dashboard_paths_from_frame_analysis(frame_analysis)
    if not paths:
        return {
            "attempted": True,
            "available": False,
            "reason": "no dashboard candidates",
            "candidates_used": [],
            "expected": expected.get("odometer"),
        }

    reader = OdometerReader()
    if not getattr(reader, "ocr_available", False) and not getattr(reader, "use_gemini", False):
        return {
            "attempted": True,
            "available": False,
            "reason": "no OCR engine or Gemini vision fallback available",
            "candidates_used": paths,
            "expected": expected.get("odometer"),
        }

    result = await reader.read(paths)
    result = dict(result or {})
    result.update({
        "attempted": True,
        "available": result.get("value") is not None,
        "candidates_used": paths,
        "expected": expected.get("odometer"),
    })
    if result.get("value") is None and not result.get("reason"):
        result["reason"] = result.get("reasoning") or "no odometer value returned"
    result["validation"] = _validate_odometer(result, expected.get("odometer"))
    return result


def _dashboard_paths_from_frame_analysis(frame_analysis: Dict[str, Any]) -> List[str]:
    paths: List[str] = []
    for item in frame_analysis.get("dashboard_candidates") or []:
        if not isinstance(item, dict):
            continue
        path = (
            item.get("readout_crop_path")
            or item.get("crop_path")
            or item.get("organized_path")
            or item.get("frame")
        )
        if path and path not in paths and Path(path).exists():
            paths.append(path)

    angle_shots = frame_analysis.get("angle_shots") or {}
    for view in ("odometer", "dashboard", "interior"):
        item = angle_shots.get(view) or {}
        if not isinstance(item, dict):
            continue
        path = (
            item.get("readout_crop_path")
            or item.get("crop_path")
            or item.get("organized_path")
            or item.get("frame")
        )
        if path and path not in paths and Path(path).exists():
            paths.append(path)
    return paths[:8]


def _validate_odometer(odometer_ocr: Dict[str, Any] | None, expected_spec: Any) -> Dict[str, Any] | None:
    if expected_spec is None:
        return None

    if isinstance(expected_spec, (int, float)):
        expected_value = int(expected_spec)
        tolerance = 0
    elif isinstance(expected_spec, dict):
        raw_value = expected_spec.get("value")
        if raw_value is None:
            return None
        expected_value = int(raw_value)
        tolerance = int(expected_spec.get("tolerance", 0) or 0)
    else:
        return None

    actual_value = None if not odometer_ocr else odometer_ocr.get("value")
    try:
        actual_int = int(actual_value)
    except (TypeError, ValueError):
        actual_int = None

    matched = actual_int is not None and abs(actual_int - expected_value) <= tolerance
    return {
        "expected": expected_value,
        "actual": actual_int,
        "tolerance": tolerance,
        "matched": matched,
    }


def _expected_has_odometer(expected: Dict[str, Any]) -> bool:
    spec = expected.get("odometer")
    if isinstance(spec, (int, float)):
        return True
    if isinstance(spec, dict):
        return spec.get("value") is not None
    return False


def _frame_index_matches(selected_index: Any, spec: Any) -> bool:
    return _numeric_spec_matches(selected_index, spec)


def _selection_matches(selected: Dict[str, Any], spec: Any) -> bool:
    if not isinstance(selected, dict):
        return False
    if _frame_index_matches(selected.get("frame_index"), spec):
        return True
    if not isinstance(spec, dict):
        return False

    field_specs = (
        ("frame_index", ("frame_index", "indices")),
        ("extracted_index", ("extracted_index", "extracted_indices")),
        ("source_frame_index", ("source_frame_index", "source_frame_indices")),
        ("timestamp_seconds", ("timestamp_seconds", "timestamp_range_seconds")),
    )
    explicit_checks = []
    for selected_key, spec_keys in field_specs:
        for spec_key in spec_keys:
            if spec_key in spec:
                explicit_checks.append(_numeric_spec_matches(selected.get(selected_key), spec.get(spec_key)))
                break
    if explicit_checks:
        return all(explicit_checks)
    return False


def _numeric_spec_matches(selected_index: Any, spec: Any) -> bool:
    if selected_index is None:
        return False
    try:
        selected = float(selected_index)
    except (TypeError, ValueError):
        return False

    if isinstance(spec, (int, float)):
        return selected == spec
    if isinstance(spec, list):
        if len(spec) == 2 and all(isinstance(item, (int, float)) for item in spec):
            return float(spec[0]) <= selected <= float(spec[1])
        return selected in {float(item) for item in spec if isinstance(item, (int, float))}
    if isinstance(spec, dict):
        if "indices" in spec and isinstance(spec["indices"], list):
            return selected in {float(item) for item in spec["indices"] if isinstance(item, (int, float))}
        if "values" in spec and isinstance(spec["values"], list):
            return selected in {float(item) for item in spec["values"] if isinstance(item, (int, float))}
        if "value" in spec and isinstance(spec.get("value"), (int, float)):
            tolerance = float(spec.get("tolerance", spec.get("tolerance_seconds", 0)) or 0)
            return abs(selected - float(spec["value"])) <= tolerance
        min_idx = spec.get("min")
        max_idx = spec.get("max")
        if min_idx is not None or max_idx is not None:
            lower_ok = True if min_idx is None else selected >= float(min_idx)
            upper_ok = True if max_idx is None else selected <= float(max_idx)
            return lower_ok and upper_ok
    return False


def _compact_item(item: Any) -> Dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    keys = (
        "view",
        "frame",
        "organized_path",
        "crop_path",
        "readout_crop_path",
        "frame_index",
        "extracted_index",
        "source_frame_index",
        "timestamp_seconds",
        "score",
        "quality_score",
        "vehicle_ratio",
        "dashboard_score",
        "clip_score",
        "temporal_score",
        "high_confidence",
        "semantic_source",
        "candidate_role",
    )
    return {key: item.get(key) for key in keys if item.get(key) is not None}


def _write_contact_sheet(
    frame_paths: List[str],
    manifest: Dict[str, Any],
    output_path: Path,
    thumb_width: int = 260,
    columns: int = 4,
) -> None:
    if not frame_paths:
        return

    markers_by_index = _markers_by_frame_index(manifest)
    metadata_by_index = _metadata_by_extracted_index(manifest.get("frame_metadata") or {})
    thumbs = []
    label_height = 30
    thumb_width = max(int(thumb_width), 120)
    columns = max(int(columns), 1)

    for index, frame_path in enumerate(frame_paths):
        image = cv2.imread(frame_path)
        if image is None:
            image = _blank_tile(thumb_width, int(thumb_width * 9 / 16) + label_height, f"#{index} unreadable")
            thumbs.append(image)
            continue

        h, w = image.shape[:2]
        scale = thumb_width / max(w, 1)
        thumb_height = max(int(h * scale), 1)
        resized = cv2.resize(image, (thumb_width, thumb_height), interpolation=cv2.INTER_AREA)
        tile = cv2.copyMakeBorder(
            resized,
            label_height,
            0,
            0,
            0,
            cv2.BORDER_CONSTANT,
            value=(245, 245, 245),
        )
        markers = markers_by_index.get(index, [])
        frame_meta = metadata_by_index.get(index, {})
        timestamp = frame_meta.get("timestamp_seconds")
        label = f"#{index}"
        if isinstance(timestamp, (int, float)):
            label = f"{label} {timestamp:.1f}s"
        if markers:
            label = f"{label} {'/'.join(markers)}"
            cv2.rectangle(tile, (0, 0), (thumb_width - 1, tile.shape[0] - 1), (0, 170, 255), 4)
        cv2.putText(
            tile,
            label[:42],
            (8, 21),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.58,
            (20, 20, 20),
            2,
            cv2.LINE_AA,
        )
        thumbs.append(tile)

    max_height = max(tile.shape[0] for tile in thumbs)
    padded = [_pad_tile(tile, thumb_width, max_height) for tile in thumbs]
    rows = []
    for start in range(0, len(padded), columns):
        row_tiles = padded[start:start + columns]
        while len(row_tiles) < columns:
            row_tiles.append(_blank_tile(thumb_width, max_height, ""))
        rows.append(cv2.hconcat(row_tiles))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), cv2.vconcat(rows))


def _write_annotation_template(frame_paths: List[str], manifest: Dict[str, Any], output_path: Path) -> None:
    angle_shots = manifest.get("angle_shots") or {}
    dashboard_candidates = manifest.get("dashboard_candidates") or []
    template = {
        "_instructions": [
            "Fill each view with acceptable extracted-frame indices from the contact sheet.",
            "Use either [min, max], {\"indices\": [1, 2, 3]}, or a single index.",
            "You may also use {\"source_frame_index\": [120, 180]} or {\"timestamp_seconds\": {\"value\": 10.5, \"tolerance_seconds\": 0.75}}.",
            "The root dashboard field is matched against dashboard_candidates.",
            "Optional inspection fields are validated against --inspection-json from a full ML process response.",
        ],
        "_source_manifest": str(Path(manifest.get("output_dir", "")) / "frame_analysis_manifest.json"),
        "_frames_extracted": len(frame_paths),
        "_frame_metadata": manifest.get("frame_metadata", {}).get("frames", []),
        "_selected_indices": {
            view: item.get("frame_index")
            for view, item in angle_shots.items()
            if isinstance(item, dict)
        },
        "_dashboard_candidate_indices": [
            item.get("frame_index")
            for item in dashboard_candidates
            if isinstance(item, dict)
        ],
        "views": {
            view: {"indices": []}
            for view in [*EXTERIOR_VIEWS, "interior", "dashboard", "odometer"]
        },
        "dashboard": {"indices": []},
        "odometer": {
            "value": None,
            "tolerance": 0,
        },
        "inspection": {
            "vehicle": {
                "brand": None,
                "model": None,
                "year": None,
                "variant": None,
                "type": None,
                "color": None,
            },
            "overall_condition": None,
            "visual_analysis": {
                "available": None,
            },
            "damage_items": [
                {
                    "type": None,
                    "location": None,
                    "severity": None,
                }
            ],
            "modification_items": [
                {
                    "part": None,
                    "status": None,
                }
            ],
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(template, indent=2), encoding="utf-8")


def _markers_by_frame_index(manifest: Dict[str, Any]) -> Dict[int, List[str]]:
    markers: Dict[int, List[str]] = {}
    for view, item in (manifest.get("angle_shots") or {}).items():
        if not isinstance(item, dict):
            continue
        _append_marker(markers, item.get("frame_index"), view)

    for i, item in enumerate(manifest.get("dashboard_candidates") or [], start=1):
        if not isinstance(item, dict):
            continue
        _append_marker(markers, item.get("frame_index"), f"dash{i}")
    return markers


def _metadata_by_extracted_index(frame_metadata: Dict[str, Any]) -> Dict[int, Dict[str, Any]]:
    out: Dict[int, Dict[str, Any]] = {}
    for item in frame_metadata.get("frames") or []:
        if not isinstance(item, dict):
            continue
        try:
            index = int(item.get("extracted_index"))
        except (TypeError, ValueError):
            continue
        out[index] = item
    return out


def _append_marker(markers: Dict[int, List[str]], raw_index: Any, label: str) -> None:
    try:
        index = int(raw_index)
    except (TypeError, ValueError):
        return
    markers.setdefault(index, [])
    if label not in markers[index]:
        markers[index].append(label)


def _blank_tile(width: int, height: int, label: str) -> Any:
    tile = 255 * np.ones((height, width, 3), dtype="uint8")
    if label:
        cv2.putText(tile, label, (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (20, 20, 20), 2, cv2.LINE_AA)
    return tile


def _pad_tile(tile: Any, width: int, height: int) -> Any:
    bottom = max(height - tile.shape[0], 0)
    right = max(width - tile.shape[1], 0)
    if bottom == 0 and right == 0:
        return tile
    return cv2.copyMakeBorder(tile, 0, bottom, 0, right, cv2.BORDER_CONSTANT, value=(255, 255, 255))


def _print_summary(manifest: Dict[str, Any], manifest_path: Path) -> None:
    summary = manifest["summary"]
    print("=" * 72)
    print("Video Understanding Evaluation")
    print("=" * 72)
    print(f"Video: {manifest['video']}")
    print(f"Manifest: {manifest_path}")
    print(f"Frames extracted: {summary['frames_extracted']}")
    print(f"Organizer method: {summary['organizer_method']}")
    print(f"Coverage: {summary['coverage_ratio']:.0%}")
    print(f"High-confidence coverage: {summary['high_confidence_coverage_ratio']:.0%}")
    print(f"Present views: {', '.join(summary['present_views']) or 'none'}")
    print(f"High-confidence views: {', '.join(summary['high_confidence_views']) or 'none'}")
    print(f"Low-confidence views: {', '.join(summary['low_confidence_views']) or 'none'}")
    print(f"Missing views: {', '.join(summary['missing_views']) or 'none'}")
    print(f"Dashboard candidates: {summary['dashboard_candidates']}")
    print(f"Representative frames: {summary['representative_frames']}")
    artifacts = manifest.get("artifacts") or {}
    if artifacts.get("contact_sheet"):
        print(f"Contact sheet: {artifacts['contact_sheet']}")
    if artifacts.get("annotation_template"):
        print(f"Annotation template: {artifacts['annotation_template']}")
    if manifest.get("validation"):
        validation = manifest["validation"]
        if validation.get("view_accuracy") is not None:
            print(
                "Annotated view accuracy: "
                f"{validation['matched_views']}/{validation['total_views']} "
                f"({validation['view_accuracy']:.0%})"
            )
        if validation.get("dashboard"):
            print(f"Annotated dashboard match: {validation['dashboard']['matched']}")
        if validation.get("odometer"):
            print(f"Annotated odometer match: {validation['odometer']['matched']}")
        if validation.get("inspection"):
            print(f"Annotated inspection match: {validation['inspection']['matched']}")
    if manifest.get("odometer_ocr"):
        odometer = manifest["odometer_ocr"]
        if odometer.get("available"):
            print(f"Odometer OCR: {odometer.get('value')} ({float(odometer.get('confidence') or 0):.0%})")
        else:
            print(f"Odometer OCR unavailable: {odometer.get('reason')}")
    print("=" * 72)


def _exit_code(manifest: Dict[str, Any], args: argparse.Namespace) -> int:
    summary = manifest["summary"]
    coverage_ok = float(summary.get("coverage_ratio") or 0.0) >= args.min_coverage
    high_confidence_threshold = _effective_high_confidence_threshold(args)
    high_confidence_ok = (
        float(summary.get("high_confidence_coverage_ratio") or 0.0)
        >= high_confidence_threshold
    )
    dashboard_ok = int(summary.get("dashboard_candidates") or 0) >= args.min_dashboard_candidates
    frames_ok = int(summary.get("frames_extracted") or 0) > 0
    validation = manifest.get("validation") or {}
    if validation:
        view_accuracy = validation.get("view_accuracy")
        views_ok = view_accuracy is None or float(view_accuracy) >= args.min_view_accuracy
        dashboard_result = validation.get("dashboard") or {}
        annotated_dashboard_ok = dashboard_result.get("matched") is not False
        odometer_result = validation.get("odometer") or {}
        annotated_odometer_ok = odometer_result.get("matched") is not False
        inspection_result = validation.get("inspection") or {}
        annotated_inspection_ok = inspection_result.get("matched") is not False
    else:
        views_ok = True
        annotated_dashboard_ok = True
        annotated_odometer_ok = True
        annotated_inspection_ok = True

    odometer_ocr = manifest.get("odometer_ocr") or {}
    if args.read_odometer or odometer_ocr:
        odometer_available_ok = odometer_ocr.get("available") is not False
        odometer_confidence_ok = float(odometer_ocr.get("confidence") or 0.0) >= args.min_odometer_confidence
    else:
        odometer_available_ok = True
        odometer_confidence_ok = True

    visual_analysis = (manifest.get("inspection") or {}).get("visual_analysis") or {}
    require_visual_analysis = bool(getattr(args, "require_visual_analysis", False))
    visual_analysis_ok = (
        not require_visual_analysis
        or bool(visual_analysis.get("available"))
    )

    if (
        frames_ok
        and coverage_ok
        and high_confidence_ok
        and dashboard_ok
        and views_ok
        and annotated_dashboard_ok
        and annotated_odometer_ok
        and annotated_inspection_ok
        and odometer_available_ok
        and odometer_confidence_ok
        and visual_analysis_ok
    ):
        print("PASS: video-understanding checks met configured thresholds")
        return 0

    print("FAIL: video-understanding checks did not meet configured thresholds")
    if not frames_ok:
        print("- no frames extracted")
    if not coverage_ok:
        print(f"- coverage below threshold: {summary.get('coverage_ratio')} < {args.min_coverage}")
    if not high_confidence_ok:
        print(
            "- high-confidence coverage below threshold: "
            f"{summary.get('high_confidence_coverage_ratio')} < {high_confidence_threshold}"
        )
    if not dashboard_ok:
        print(
            "- dashboard candidates below threshold: "
            f"{summary.get('dashboard_candidates')} < {args.min_dashboard_candidates}"
        )
    if not views_ok:
        print(f"- annotated view accuracy below threshold: {validation.get('view_accuracy')} < {args.min_view_accuracy}")
    if not annotated_dashboard_ok:
        print("- no dashboard candidate matched the annotated dashboard frame range")
    if not annotated_odometer_ok:
        print("- odometer OCR did not match the expected odometer value")
    if not annotated_inspection_ok:
        print("- inspection payload did not match expected vehicle/condition/damage/modification annotations")
    if not odometer_available_ok:
        print(f"- odometer OCR unavailable: {odometer_ocr.get('reason')}")
    if not odometer_confidence_ok:
        print(
            "- odometer OCR confidence below threshold: "
            f"{odometer_ocr.get('confidence')} < {args.min_odometer_confidence}"
        )
    if not visual_analysis_ok:
        reason = visual_analysis.get("reason") or "inspection payload missing Gemini/visual analysis availability"
        print(f"- required visual analysis unavailable: {reason}")
    return 2


def _effective_high_confidence_threshold(args: argparse.Namespace) -> float:
    configured = getattr(args, "min_high_confidence_coverage", None)
    if configured is not None:
        return float(configured)
    return 0.5 if getattr(args, "with_models", False) else 0.0


def _default_output_dir(video_path: Path) -> Path:
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    return Path.cwd() / "evaluation-output" / f"{video_path.stem}-{timestamp}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate frame extraction and organization for a vehicle walkaround video.")
    parser.add_argument("video", help="Path to the walkaround video")
    parser.add_argument("--output-dir", help="Directory for extracted frames and manifest")
    parser.add_argument("--manifest-name", default="frame_analysis_manifest.json")
    parser.add_argument("--fps", type=float, default=FRAME_EXTRACTION["fps"], help="Frame extraction rate")
    parser.add_argument("--blur-threshold", type=float, default=FRAME_EXTRACTION["min_blur_threshold"])
    parser.add_argument("--jpeg-quality", type=int, default=FRAME_EXTRACTION["jpeg_quality"])
    parser.add_argument("--with-models", action="store_true", help="Load YOLO + CLIP for semantic view scoring")
    parser.add_argument(
        "--inspection-json",
        help="Optional full ML process response/report JSON for validating vehicle, condition, damage, and modifications.",
    )
    parser.add_argument(
        "--require-visual-analysis",
        action="store_true",
        help="Fail when --inspection-json does not show an available Gemini/VLM visual analysis pass.",
    )
    parser.add_argument(
        "--expected-json",
        help=(
            "Optional annotations JSON. Schema: "
            '{"views":{"front":[0,3],"rear":{"min":12,"max":15}},"dashboard":[24,28]}'
        ),
    )
    parser.add_argument("--min-coverage", type=float, default=0.75)
    parser.add_argument(
        "--min-high-confidence-coverage",
        type=float,
        default=None,
        help="Minimum high-confidence coverage. Defaults to 0.5 with --with-models and 0.0 without models.",
    )
    parser.add_argument("--min-dashboard-candidates", type=int, default=1)
    parser.add_argument("--min-view-accuracy", type=float, default=0.8)
    parser.add_argument("--read-odometer", action="store_true", help="Run OCR on organized dashboard candidates")
    parser.add_argument(
        "--min-odometer-confidence",
        type=float,
        default=0.5,
        help="Minimum OCR confidence required when --read-odometer is used.",
    )
    parser.add_argument("--write-annotation-artifacts", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--contact-sheet-name", default="frame_contact_sheet.jpg")
    parser.add_argument("--annotation-template-name", default="annotation_template.json")
    parser.add_argument("--contact-sheet-thumb-width", type=int, default=260)
    parser.add_argument("--contact-sheet-columns", type=int, default=4)
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
