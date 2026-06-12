"""
Audit whether the vehicle video-understanding pipeline has enough evidence to
be considered complete for a real walkaround video.

This is intentionally stricter than unit tests: it maps the product objective
to concrete artifacts such as evaluator manifests, readiness JSON, and saved
process responses. Missing evidence fails closed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List


def build_completion_audit(
    *,
    manifest: Dict[str, Any] | None = None,
    inspection: Dict[str, Any] | None = None,
    readiness: Dict[str, Any] | None = None,
    min_coverage: float = 0.75,
    min_temporal_coverage: float = 0.90,
    min_high_confidence_coverage: float = 0.50,
    min_selected_quality: float = 0.40,
    min_dashboard_candidates: int = 1,
    min_odometer_confidence: float = 0.50,
    min_vehicle_confidence: float = 0.70,
    min_modification_part_categories: int = 3,
    require_live_vlm: bool = True,
) -> Dict[str, Any]:
    manifest = manifest or {}
    inspection = inspection or {}
    readiness = readiness or {}
    summary = manifest.get("summary") or {}
    config = manifest.get("configuration") or {}
    temporal_evidence = _extract_temporal_coverage_evidence(manifest, min_temporal_coverage)
    named_view_evidence = _extract_named_view_evidence(manifest)
    selected_quality_evidence = _extract_selected_frame_quality_evidence(
        manifest,
        min_selected_quality,
    )
    odometer = _extract_odometer(manifest, inspection)
    visual = _extract_visual_analysis(inspection)
    vehicle = _extract_vehicle(inspection)
    damage_items = _extract_damage_items(inspection)
    damage_evidence = _extract_damage_category_evidence(inspection, damage_items)
    section_routing_evidence = _extract_section_routing_evidence(inspection)
    modification_items = _extract_modification_items(inspection)
    modification_evidence = _extract_modification_evidence(
        modification_items,
        min_modification_part_categories,
    )

    checks = [
        _check(
            "frame_extraction",
            int(summary.get("frames_extracted") or 0) > 0,
            "Extract frames from the uploaded walkaround video.",
            evidence={"frames_extracted": summary.get("frames_extracted")},
        ),
        _check(
            "model_backed_video_analysis",
            bool(config.get("with_models")) and "clip" in str(summary.get("organizer_method") or ""),
            "Analyze frames with CLIP/YOLO or equivalent model-backed scoring.",
            evidence={
                "with_models": config.get("with_models"),
                "organizer_method": summary.get("organizer_method"),
            },
        ),
        _check(
            "full_video_temporal_coverage",
            bool(temporal_evidence["passed"]),
            "Sample frames across the full uploaded walkaround video duration.",
            evidence=temporal_evidence,
        ),
        _check(
            "vehicle_angle_coverage",
            float(summary.get("coverage_ratio") or 0.0) >= min_coverage,
            "Extract representative front/rear/side/quarter/dashboard angle shots.",
            evidence={
                "coverage_ratio": summary.get("coverage_ratio"),
                "missing_views": summary.get("missing_views"),
                "threshold": min_coverage,
            },
        ),
        _check(
            "named_view_coverage",
            bool(named_view_evidence["has_required_named_views"]),
            "Extract each named walkaround view: front, rear, sides, quarters, interior, and dashboard.",
            evidence=named_view_evidence,
        ),
        _check(
            "high_confidence_angle_coverage",
            float(summary.get("high_confidence_coverage_ratio") or 0.0) >= min_high_confidence_coverage,
            "Selected angles should have enough high-confidence model/quality evidence.",
            evidence={
                "high_confidence_coverage_ratio": summary.get("high_confidence_coverage_ratio"),
                "low_confidence_views": summary.get("low_confidence_views"),
                "threshold": min_high_confidence_coverage,
            },
        ),
        _check(
            "selected_frame_quality",
            bool(selected_quality_evidence["passed"]),
            "Selected angle/dashboard shots must have usable image paths and quality scores.",
            evidence=selected_quality_evidence,
        ),
        _check(
            "dashboard_odometer_candidates",
            int(summary.get("dashboard_candidates") or 0) >= min_dashboard_candidates,
            "Detect dashboard/odometer frames for OCR and VLM.",
            evidence={
                "dashboard_candidates": summary.get("dashboard_candidates"),
                "threshold": min_dashboard_candidates,
            },
        ),
        _check(
            "odometer_verified",
            odometer.get("value") is not None
            and float(odometer.get("confidence") or 0.0) >= min_odometer_confidence,
            "Read the odometer accurately enough to accept without manual review.",
            evidence={
                "value": odometer.get("value"),
                "confidence": odometer.get("confidence"),
                "threshold": min_odometer_confidence,
                "reason": odometer.get("reason") or odometer.get("notes"),
            },
        ),
        _check(
            "vlm_available",
            bool(visual.get("available")) and (
                not require_live_vlm
                or bool((readiness.get("capabilities") or {}).get("llm_vlm_analysis"))
            ),
            "Send organized frames and metadata to a live LLM/VLM analysis path.",
            evidence={
                "visual_analysis_available": visual.get("available"),
                "visual_analysis_reason": visual.get("reason"),
                "readiness_llm_vlm_analysis": (readiness.get("capabilities") or {}).get("llm_vlm_analysis"),
                "gemini_ready": ((readiness.get("checks") or {}).get("gemini") or {}).get("ready"),
                "gemini_live_reason": (((readiness.get("checks") or {}).get("gemini") or {}).get("live") or {}).get("reason"),
                "openai_ready": ((readiness.get("checks") or {}).get("openai") or {}).get("ready"),
                "require_live_vlm": require_live_vlm,
            },
        ),
        _check(
            "vehicle_identity",
            all(vehicle.get(field) not in (None, "") for field in ("brand", "model", "year", "variant", "type"))
            and _extract_vehicle_category(vehicle) not in (None, "")
            and float(vehicle.get("confidence") or 0.0) >= min_vehicle_confidence,
            "Determine maker, model, year, trim/version, and vehicle type/category.",
            evidence={
                **{field: vehicle.get(field) for field in ("brand", "model", "year", "variant", "type")},
                "vehicle_category": _extract_vehicle_category(vehicle),
                "year_range": vehicle.get("year_range"),
                "variant_candidates": vehicle.get("variant_candidates"),
                "identity_source": vehicle.get("identity_source"),
                "identity_override_fields": vehicle.get("identity_override_fields"),
                "vin_supplied": vehicle.get("vin") not in (None, ""),
                "registration_supplied": vehicle.get("registration") not in (None, ""),
                "identity_notes": vehicle.get("identity_notes"),
                "confidence": vehicle.get("confidence"),
                "threshold": min_vehicle_confidence,
            },
        ),
        _check(
            "condition_assessment",
            _extract_condition(inspection) not in (None, ""),
            "Determine exterior condition from extracted frames.",
            evidence={"overall_condition": _extract_condition(inspection)},
        ),
        _check(
            "damage_detection",
            bool(damage_evidence["has_required_categories"])
            and damage_evidence.get("severity") not in (None, ""),
            "Detect scratches, dents, rust, cracks, paint damage, locations, and severity.",
            evidence=damage_evidence,
        ),
        _check(
            "inspection_section_routing",
            bool(section_routing_evidence["has_routed_sections"])
            and bool(section_routing_evidence["has_required_confidence"]),
            "Route validated inspection images into confidence-aware vehicle sections.",
            evidence=section_routing_evidence,
        ),
        _check(
            "modification_detection",
            bool(modification_evidence["passed"]),
            "Detect stock versus modified parts across multiple visible part categories.",
            evidence=modification_evidence,
        ),
        _check(
            "inspection_summary",
            _extract_summary(inspection) not in (None, ""),
            "Generate an overall inspection summary.",
            evidence={"summary_present": _extract_summary(inspection) not in (None, "")},
        ),
    ]

    passed = all(item["passed"] for item in checks)
    return {
        "status": "complete" if passed else "incomplete",
        "passed": passed,
        "checks": checks,
        "missing": [item["id"] for item in checks if not item["passed"]],
    }


def _check(check_id: str, passed: bool, requirement: str, evidence: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": check_id,
        "requirement": requirement,
        "passed": bool(passed),
        "evidence": evidence,
    }


def _extract_named_view_evidence(manifest: Dict[str, Any]) -> Dict[str, Any]:
    required = [
        "front",
        "front-left",
        "left",
        "rear-left",
        "rear",
        "rear-right",
        "right",
        "front-right",
        "interior",
        "dashboard",
    ]
    angle_shots = manifest.get("angle_shots") if isinstance(manifest.get("angle_shots"), dict) else {}
    summary = manifest.get("summary") if isinstance(manifest.get("summary"), dict) else {}
    present = set(summary.get("present_views") or [])
    present.update(view for view, payload in angle_shots.items() if payload)

    dashboard_present = (
        "dashboard" in present
        or "odometer" in present
        or bool(manifest.get("dashboard_candidates"))
    )
    normalized_present = sorted(present | ({"dashboard"} if dashboard_present else set()))
    missing = [view for view in required if view not in normalized_present]

    return {
        "required_named_views": required,
        "present_named_views": normalized_present,
        "missing_named_views": missing,
        "dashboard_candidates": len(manifest.get("dashboard_candidates") or []),
        "has_required_named_views": len(missing) == 0,
    }


def _extract_temporal_coverage_evidence(
    manifest: Dict[str, Any],
    min_temporal_coverage: float,
) -> Dict[str, Any]:
    metadata = manifest.get("frame_metadata") if isinstance(manifest.get("frame_metadata"), dict) else {}
    frames = [item for item in metadata.get("frames") or [] if isinstance(item, dict)]
    timestamps = [
        float(item["timestamp_seconds"])
        for item in frames
        if item.get("timestamp_seconds") is not None
    ]
    video_fps = float(metadata.get("video_fps") or 0.0)
    total_source_frames = int(metadata.get("total_source_frames") or 0)
    duration = (
        total_source_frames / video_fps
        if video_fps > 0 and total_source_frames > 0
        else None
    )
    first_timestamp = min(timestamps) if timestamps else None
    last_timestamp = max(timestamps) if timestamps else None
    ratio = (
        float(last_timestamp) / duration
        if duration and last_timestamp is not None and duration > 0
        else None
    )

    return {
        "frames_extracted": metadata.get("frames_extracted", len(frames)),
        "video_duration_seconds": round(duration, 3) if duration is not None else None,
        "first_timestamp_seconds": first_timestamp,
        "last_timestamp_seconds": last_timestamp,
        "temporal_coverage_ratio": round(ratio, 4) if ratio is not None else None,
        "threshold": min_temporal_coverage,
        "passed": bool(frames)
        and first_timestamp is not None
        and first_timestamp <= 2.0
        and ratio is not None
        and ratio >= min_temporal_coverage,
    }


def _extract_selected_frame_quality_evidence(
    manifest: Dict[str, Any],
    min_selected_quality: float,
) -> Dict[str, Any]:
    angle_shots = manifest.get("angle_shots") if isinstance(manifest.get("angle_shots"), dict) else {}
    dashboard_candidates = (
        manifest.get("dashboard_candidates")
        if isinstance(manifest.get("dashboard_candidates"), list)
        else []
    )
    selected = [
        item
        for item in list(angle_shots.values()) + dashboard_candidates
        if isinstance(item, dict)
    ]
    missing_paths = [
        item.get("view") or f"selected_{index}"
        for index, item in enumerate(selected)
        if not (item.get("organized_path") or item.get("frame"))
    ]
    missing_quality = [
        item.get("view") or f"selected_{index}"
        for index, item in enumerate(selected)
        if item.get("quality_score") is None
    ]
    low_quality = [
        {
            "view": item.get("view") or f"selected_{index}",
            "quality_score": item.get("quality_score"),
        }
        for index, item in enumerate(selected)
        if item.get("quality_score") is not None
        and float(item.get("quality_score") or 0.0) < min_selected_quality
    ]

    return {
        "selected_frames": len(selected),
        "threshold": min_selected_quality,
        "missing_paths": missing_paths,
        "missing_quality": missing_quality,
        "low_quality": low_quality,
        "min_quality": min(
            [float(item.get("quality_score")) for item in selected if item.get("quality_score") is not None],
            default=None,
        ),
        "passed": bool(selected)
        and not missing_paths
        and not missing_quality
        and not low_quality,
    }


def _extract_odometer(manifest: Dict[str, Any], inspection: Dict[str, Any]) -> Dict[str, Any]:
    for candidate in (
        manifest.get("odometer_ocr"),
        inspection.get("odometer"),
        inspection.get("odometer_info"),
        (inspection.get("report") or {}).get("odometer_reading") if isinstance(inspection.get("report"), dict) else None,
    ):
        if isinstance(candidate, dict) and candidate:
            if "reading" in candidate and "value" not in candidate:
                return {"value": candidate.get("reading"), **candidate}
            return candidate
    return {}


def _extract_visual_analysis(inspection: Dict[str, Any]) -> Dict[str, Any]:
    for candidate in (
        inspection.get("gemini_analysis"),
        inspection.get("visual_analysis"),
        (inspection.get("report") or {}).get("visual_analysis") if isinstance(inspection.get("report"), dict) else None,
        (inspection.get("report") or {}).get("gemini_analysis") if isinstance(inspection.get("report"), dict) else None,
    ):
        if isinstance(candidate, dict) and "available" in candidate:
            return candidate
    return {"available": False, "reason": "no visual analysis evidence supplied"}


def _extract_vehicle(inspection: Dict[str, Any]) -> Dict[str, Any]:
    for candidate in (
        inspection.get("vehicle_info"),
        inspection.get("vehicle"),
        (inspection.get("gemini_analysis") or {}).get("vehicle") if isinstance(inspection.get("gemini_analysis"), dict) else None,
        (inspection.get("report") or {}).get("vehicle_details") if isinstance(inspection.get("report"), dict) else None,
    ):
        if isinstance(candidate, dict) and candidate:
            return candidate
    return {}


def _extract_vehicle_category(vehicle: Dict[str, Any]) -> Any:
    return vehicle.get("vehicle_category") or vehicle.get("category")


def _extract_condition(inspection: Dict[str, Any]) -> Any:
    candidates = [
        inspection.get("overall_condition"),
        (inspection.get("gemini_analysis") or {}).get("overall_condition") if isinstance(inspection.get("gemini_analysis"), dict) else None,
        (inspection.get("report") or {}).get("overall_condition") if isinstance(inspection.get("report"), dict) else None,
        ((inspection.get("report") or {}).get("vehicle_details") or {}).get("condition")
        if isinstance(inspection.get("report"), dict) and isinstance((inspection.get("report") or {}).get("vehicle_details"), dict)
        else None,
    ]
    return next((item for item in candidates if item not in (None, "")), None)


def _extract_damage_items(inspection: Dict[str, Any]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    gemini = inspection.get("gemini_analysis") if isinstance(inspection.get("gemini_analysis"), dict) else {}
    report = inspection.get("report") if isinstance(inspection.get("report"), dict) else {}
    report_gemini = report.get("gemini_analysis") if isinstance(report.get("gemini_analysis"), dict) else {}
    damage = inspection.get("damage") if isinstance(inspection.get("damage"), dict) else {}
    for source in (gemini.get("damage_items"), report_gemini.get("damage_items"), damage.get("locations")):
        if isinstance(source, list):
            items.extend(item for item in source if isinstance(item, dict))
    return items


def _extract_damage_category_evidence(
    inspection: Dict[str, Any],
    damage_items: List[Dict[str, Any]],
) -> Dict[str, Any]:
    damage = inspection.get("damage") if isinstance(inspection.get("damage"), dict) else {}
    required = [
        "scratches",
        "dents",
        "rust",
        "cracks",
        "paint_damage",
        "wheel_damage",
        "broken_lights",
        "missing_parts",
        "panel_misalignment",
    ]
    category_counts = {
        key: (damage.get(key) or {}).get("count")
        for key in required
        if isinstance(damage.get(key), dict)
    }
    category_detected_flags = {
        key: (damage.get(key) or {}).get("detected")
        for key in required
        if isinstance(damage.get(key), dict)
    }
    location_types = [
        str(item.get("type") or "").strip().lower()
        for item in (damage.get("locations") or [])
        if isinstance(item, dict)
    ]
    visual_types = [
        str(item.get("type") or "").strip().lower()
        for item in damage_items
        if isinstance(item, dict)
    ]

    return {
        "required_categories": required,
        "present_categories": sorted(category_counts.keys()),
        "missing_categories": [key for key in required if key not in category_counts],
        "has_required_categories": all(key in category_counts for key in required),
        "category_counts": category_counts,
        "category_detected_flags": category_detected_flags,
        "severity": damage.get("severity"),
        "damage_locations": len(damage.get("locations") or []),
        "location_types": sorted(set(location_types)),
        "visual_damage_items": len(damage_items),
        "visual_damage_types": sorted(set(visual_types)),
    }


def _extract_section_routing_evidence(inspection: Dict[str, Any]) -> Dict[str, Any]:
    report = inspection.get("report") if isinstance(inspection.get("report"), dict) else {}
    inspection_analysis = inspection.get("inspection_analysis")
    if not isinstance(inspection_analysis, dict):
        inspection_analysis = report.get("inspection_analysis") if isinstance(report.get("inspection_analysis"), dict) else {}
    if not inspection_analysis:
        return {
            "routed_images": 0,
            "present_sections": [],
            "required_any_sections": ["front", "dashboard", "wheels", "tyres", "damage-closeups"],
            "minimum_confidence": 0.35,
            "low_confidence_images": [],
            "has_required_confidence": False,
            "has_routed_sections": False,
            "not_supplied": True,
        }

    sections = inspection_analysis.get("sections") if isinstance(inspection_analysis.get("sections"), dict) else {}
    routed = [
        image
        for images in sections.values()
        if isinstance(images, list)
        for image in images
        if isinstance(image, dict)
    ]
    present = sorted(
        section
        for section, images in sections.items()
        if isinstance(images, list) and images
    )
    low_confidence = [
        {
            "section": image.get("section"),
            "frame": image.get("frame"),
            "confidence": image.get("confidence"),
        }
        for image in routed
        if float(image.get("confidence") or 0.0) < 0.35
    ]
    return {
        "routed_images": len(routed),
        "present_sections": present,
        "required_any_sections": ["front", "dashboard", "wheels", "tyres", "damage-closeups"],
        "minimum_confidence": 0.35,
        "low_confidence_images": low_confidence,
        "rejected_images": len(inspection_analysis.get("rejected_images") or []),
        "conflicts_resolved": (inspection_analysis.get("consistency") or {}).get("conflicts_resolved"),
        "has_required_confidence": bool(routed) and not low_confidence,
        "has_routed_sections": bool(routed) and bool(present),
    }


def _extract_modification_items(inspection: Dict[str, Any]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    gemini = inspection.get("gemini_analysis") if isinstance(inspection.get("gemini_analysis"), dict) else {}
    report = inspection.get("report") if isinstance(inspection.get("report"), dict) else {}
    report_gemini = report.get("gemini_analysis") if isinstance(report.get("gemini_analysis"), dict) else {}
    modification = report.get("modification_assessment") if isinstance(report.get("modification_assessment"), dict) else {}
    local_modification = (
        report.get("local_modification_analysis")
        if isinstance(report.get("local_modification_analysis"), dict)
        else {}
    )
    for source in (
        gemini.get("modification_items"),
        report_gemini.get("modification_items"),
        modification.get("items"),
        local_modification.get("items"),
    ):
        if isinstance(source, list):
            items.extend(item for item in source if isinstance(item, dict))
    return items


def _extract_modification_evidence(
    items: List[Dict[str, Any]],
    min_part_categories: int,
) -> Dict[str, Any]:
    concrete_parts = sorted({
        str(item.get("part") or "").strip().lower()
        for item in items
        if str(item.get("status") or "").strip().lower() in {"stock", "modified"}
        and str(item.get("part") or "").strip()
    })
    concrete_status_items = sum(
        1
        for item in items
        if str(item.get("status") or "").strip().lower() in {"stock", "modified"}
    )
    return {
        "modification_items": len(items),
        "concrete_status_items": concrete_status_items,
        "concrete_part_categories": concrete_parts,
        "concrete_part_category_count": len(concrete_parts),
        "threshold": min_part_categories,
        "exhaust_only": concrete_parts == ["exhaust"],
        "passed": len(concrete_parts) >= min_part_categories,
    }


def _extract_summary(inspection: Dict[str, Any]) -> Any:
    return inspection.get("summary") or (
        (inspection.get("report") or {}).get("summary")
        if isinstance(inspection.get("report"), dict)
        else None
    )


def _load_json(path: str | None) -> Dict[str, Any]:
    if not path:
        return {}
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _print_summary(audit: Dict[str, Any]) -> None:
    print("Vehicle pipeline completion audit")
    print(f"Status: {audit['status']}")
    for item in audit["checks"]:
        marker = "PASS" if item["passed"] else "FAIL"
        print(f"- {marker} {item['id']}: {item['requirement']}")
        if not item["passed"]:
            print(f"  evidence: {json.dumps(item['evidence'], sort_keys=True)}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", help="Evaluator frame_analysis_manifest.json")
    parser.add_argument("--inspection-json", help="Saved ML process response/report JSON")
    parser.add_argument("--readiness-json", help="Output from check_pipeline_readiness.py --json")
    parser.add_argument("--min-coverage", type=float, default=0.75)
    parser.add_argument("--min-temporal-coverage", type=float, default=0.90)
    parser.add_argument("--min-high-confidence-coverage", type=float, default=0.50)
    parser.add_argument("--min-selected-quality", type=float, default=0.40)
    parser.add_argument("--min-dashboard-candidates", type=int, default=1)
    parser.add_argument("--min-odometer-confidence", type=float, default=0.50)
    parser.add_argument("--min-vehicle-confidence", type=float, default=0.70)
    parser.add_argument("--min-modification-part-categories", type=int, default=3)
    parser.add_argument("--no-require-live-vlm", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    audit = build_completion_audit(
        manifest=_load_json(args.manifest),
        inspection=_load_json(args.inspection_json),
        readiness=_load_json(args.readiness_json),
        min_coverage=args.min_coverage,
        min_temporal_coverage=args.min_temporal_coverage,
        min_high_confidence_coverage=args.min_high_confidence_coverage,
        min_selected_quality=args.min_selected_quality,
        min_dashboard_candidates=args.min_dashboard_candidates,
        min_odometer_confidence=args.min_odometer_confidence,
        min_vehicle_confidence=args.min_vehicle_confidence,
        min_modification_part_categories=args.min_modification_part_categories,
        require_live_vlm=not args.no_require_live_vlm,
    )
    if args.json:
        print(json.dumps(audit, indent=2))
    else:
        _print_summary(audit)
    return 0 if audit["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
