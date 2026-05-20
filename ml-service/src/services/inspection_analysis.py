"""
Multi-stage vehicle inspection analysis and image-routing pipeline.

This layer consumes extracted/organized frame evidence plus VLM output and
produces the canonical inspection sections shown in the UI. It deliberately
keeps provider calls behind a small protocol so Gemini, OpenAI, Claude, or a
local VLM can be swapped without changing validation/routing logic.
"""

from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Protocol, Tuple


CANONICAL_SECTIONS: Tuple[str, ...] = (
    "front",
    "front-left",
    "left",
    "rear-left",
    "rear",
    "rear-right",
    "right",
    "front-right",
    "dashboard",
    "steering-wheel",
    "odometer",
    "infotainment",
    "seats",
    "trunk",
    "engine-bay",
    "wheels",
    "tyres",
    "exhaust",
    "damage-closeups",
    "needs-review",
)

SECTION_ORDER: Tuple[str, ...] = CANONICAL_SECTIONS

EXTERIOR_SECTIONS = {
    "front",
    "front-left",
    "left",
    "rear-left",
    "rear",
    "rear-right",
    "right",
    "front-right",
}
INTERIOR_SECTIONS = {"dashboard", "steering-wheel", "odometer", "infotainment", "seats"}
CLOSEUP_SECTIONS = {"trunk", "engine-bay", "wheels", "tyres", "exhaust", "damage-closeups"}
REAR_SECTIONS = {"rear", "rear-left", "rear-right"}

MIN_USABLE_QUALITY = 0.38
MIN_BACKGROUND_HEAVY_VEHICLE_RATIO = 0.03
MIN_STRONG_CONFIDENCE = 0.62

SECTION_ALIASES = {
    "front": "front",
    "front-left": "front-left",
    "front left": "front-left",
    "left-front": "front-left",
    "left front": "front-left",
    "driver front": "front-left",
    "left": "left",
    "driver side": "left",
    "side-left": "left",
    "rear-left": "rear-left",
    "rear left": "rear-left",
    "left-rear": "rear-left",
    "left rear": "rear-left",
    "rear": "rear",
    "back": "rear",
    "rear-right": "rear-right",
    "rear right": "rear-right",
    "right-rear": "rear-right",
    "right rear": "rear-right",
    "right": "right",
    "passenger side": "right",
    "side-right": "right",
    "front-right": "front-right",
    "front right": "front-right",
    "right-front": "front-right",
    "right front": "front-right",
    "interior": "seats",
    "cabin": "seats",
    "seat": "seats",
    "seats": "seats",
    "dashboard": "dashboard",
    "dash": "dashboard",
    "instrument cluster": "odometer",
    "odometer": "odometer",
    "speedometer": "odometer",
    "steering": "steering-wheel",
    "steering wheel": "steering-wheel",
    "infotainment": "infotainment",
    "screen": "infotainment",
    "center screen": "infotainment",
    "trunk": "trunk",
    "boot": "trunk",
    "engine bay": "engine-bay",
    "engine-bay": "engine-bay",
    "engine": "engine-bay",
    "wheel": "wheels",
    "wheels": "wheels",
    "rim": "wheels",
    "rims": "wheels",
    "alloy": "wheels",
    "tyre": "tyres",
    "tyres": "tyres",
    "tire": "tyres",
    "tires": "tyres",
    "exhaust": "exhaust",
    "tailpipe": "exhaust",
    "muffler": "exhaust",
    "damage": "damage-closeups",
    "damage closeup": "damage-closeups",
    "damage closeups": "damage-closeups",
    "damage close-up": "damage-closeups",
    "damage close-ups": "damage-closeups",
    "closeup": "damage-closeups",
    "close-up": "damage-closeups",
    "other": "needs-review",
    "unknown": "needs-review",
}

DAMAGE_TYPE_ALIASES = {
    "scratch": "scratch",
    "scratches": "scratch",
    "dent": "dent",
    "dents": "dent",
    "rust": "rust",
    "crack": "crack",
    "cracks": "crack",
    "paint": "paint_damage",
    "paint damage": "paint_damage",
    "paint_damage": "paint_damage",
    "broken light": "broken_light",
    "broken_light": "broken_light",
    "broken part": "broken_part",
    "broken parts": "broken_part",
    "broken_part": "broken_part",
    "missing part": "missing_part",
    "missing parts": "missing_part",
    "missing_part": "missing_part",
    "bumper damage": "bumper_damage",
    "bumper_damage": "bumper_damage",
    "wheel damage": "wheel_damage",
    "wheel_damage": "wheel_damage",
}


class InspectionVlmProvider(Protocol):
    """Provider boundary for future direct Gemini/OpenAI/Claude/local VLM use."""

    name: str

    async def analyze_inspection_images(
        self,
        images: List[Dict[str, Any]],
        frame_analysis: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Return provider-native visual analysis for normalized inspection images."""


@dataclass
class ImageCandidate:
    id: str
    frame: str
    preview_path: Optional[str]
    source_view: str
    source_group: str
    source_index: int
    quality_score: float
    vehicle_ratio: float
    foreground_bbox: Optional[List[int]]
    dashboard_score: float
    organizer_score: float
    timestamp_seconds: Optional[float]
    high_confidence: bool
    labels: List[Tuple[str, float, str]] = field(default_factory=list)
    usability: Dict[str, Any] = field(default_factory=dict)


class InspectionAnalysisPipeline:
    """Hierarchical car-inspection classifier, validator, and UI router."""

    def __init__(
        self,
        provider: Optional[InspectionVlmProvider] = None,
        *,
        min_quality: Optional[float] = None,
    ) -> None:
        self.provider = provider
        self.min_quality = min_quality if min_quality is not None else _env_float(
            "INSPECTION_ANALYSIS_MIN_QUALITY",
            MIN_USABLE_QUALITY,
        )

    async def analyze(
        self,
        *,
        frame_analysis: Dict[str, Any],
        vehicle_info: Optional[Dict[str, Any]] = None,
        damage: Optional[Dict[str, Any]] = None,
        exhaust: Optional[Dict[str, Any]] = None,
        vlm_result: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        provider_result = vlm_result or {}
        if self.provider is not None and not provider_result.get("available"):
            provider_result = await self.provider.analyze_inspection_images(
                self._provider_images(frame_analysis),
                frame_analysis,
            )
        return await asyncio.to_thread(
            self._analyze_sync,
            frame_analysis,
            vehicle_info or {},
            damage or {},
            exhaust or {},
            provider_result,
        )

    def _provider_images(self, frame_analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        images = []
        for candidate in self._collect_candidates(frame_analysis):
            images.append({
                "id": candidate.id,
                "frame": candidate.frame,
                "preview_path": candidate.preview_path,
                "expected_view": candidate.source_view,
                "quality_score": candidate.quality_score,
                "vehicle_ratio": candidate.vehicle_ratio,
                "foreground_bbox": candidate.foreground_bbox,
                "timestamp_seconds": candidate.timestamp_seconds,
            })
        return images

    def _analyze_sync(
        self,
        frame_analysis: Dict[str, Any],
        vehicle_info: Dict[str, Any],
        damage: Dict[str, Any],
        exhaust: Dict[str, Any],
        vlm_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        candidates = self._collect_candidates(frame_analysis)
        vlm_by_path, vlm_by_view = self._index_vlm_frames(vlm_result)
        damage_items = self._normalize_damage_items(damage, vlm_result)
        damage_frames = {
            str(item.get("frame"))
            for item in damage_items
            if item.get("frame")
        }

        resolved_images = []
        rejected_images = []
        conflicts = []
        for candidate in candidates:
            evidence = self._evidence_for(candidate, vlm_by_path, vlm_by_view)
            candidate.labels.extend(self._labels_from_evidence(candidate, evidence, damage_frames))
            candidate.usability = self._score_usability(candidate)
            route, route_conflicts = self._route_candidate(candidate, evidence)
            conflicts.extend(route_conflicts)
            if candidate.usability["usable"] and route["section"] != "needs-review":
                resolved_images.append(route)
            else:
                rejected = dict(route)
                rejected["section"] = "needs-review"
                rejected["rejected_reasons"] = candidate.usability["reasons"] or route_conflicts
                rejected_images.append(rejected)

        sections = self._group_sections(resolved_images)
        duplicates = self._resolve_duplicates(sections)
        vehicle = self._vehicle_payload(vehicle_info, vlm_result)
        validation = self._validation_summary(sections, rejected_images, conflicts, duplicates)

        return {
            "available": True,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "provider": self._provider_name(vlm_result),
            "section_order": list(SECTION_ORDER),
            "sections": sections,
            "images": resolved_images,
            "rejected_images": rejected_images,
            "vehicle": vehicle,
            "damage_detections": damage_items,
            "consistency": validation,
            "stages": {
                "stage_1": {
                    "name": "vehicle_existence_usability_foreground",
                    "images_checked": len(candidates),
                    "usable_images": len(resolved_images),
                    "rejected_images": len(rejected_images),
                    "min_quality": self.min_quality,
                    "foreground_metric": "organizer_yolo_vehicle_ratio",
                },
                "stage_2": {
                    "name": "interior_exterior_closeup",
                    "groups": self._count_groups(resolved_images),
                },
                "stage_3": {
                    "name": "exact_section_classification",
                    "sections_with_images": [section for section, items in sections.items() if items],
                },
                "stage_4": {
                    "name": "vehicle_identity",
                    "confidence": vehicle.get("confidence"),
                    "source": vehicle.get("source"),
                },
                "stage_5": {
                    "name": "damage_detection_localization",
                    "damage_count": len(damage_items),
                    "damage_types": sorted({item["type"] for item in damage_items if item.get("type")}),
                },
            },
            "raw_model_responses": self._raw_model_payload(vlm_result),
        }

    def _collect_candidates(self, frame_analysis: Dict[str, Any]) -> List[ImageCandidate]:
        candidates: List[ImageCandidate] = []
        seen = set()

        def add(source: Dict[str, Any], source_view: str, source_group: str, index: int) -> None:
            if not isinstance(source, dict):
                return
            frame = source.get("inspection_path") or source.get("organized_path") or source.get("frame")
            if not frame:
                return
            key = str(frame)
            if key in seen:
                return
            seen.add(key)
            candidates.append(
                ImageCandidate(
                    id=f"{source_group}:{source_view}:{index}",
                    frame=key,
                    preview_path=source.get("preview_path") or source.get("inspection_path") or source.get("organized_path"),
                    source_view=source.get("view") or source_view,
                    source_group=source_group,
                    source_index=index,
                    quality_score=_safe_float(source.get("quality_score")),
                    vehicle_ratio=_safe_float(source.get("vehicle_ratio")),
                    foreground_bbox=_safe_bbox(source.get("vehicle_bbox") or source.get("foreground_bbox")),
                    dashboard_score=_safe_float(source.get("dashboard_score")),
                    organizer_score=_safe_float(source.get("score")),
                    timestamp_seconds=_safe_optional_float(source.get("timestamp_seconds")),
                    high_confidence=bool(source.get("high_confidence")),
                )
            )

        angle_shots = frame_analysis.get("angle_shots") if isinstance(frame_analysis.get("angle_shots"), dict) else {}
        for index, section in enumerate(SECTION_ORDER):
            if section == "needs-review":
                continue
            add(angle_shots.get(section) or {}, section, "angle", index)
        for index, (view, payload) in enumerate(angle_shots.items()):
            if view not in SECTION_ORDER:
                add(payload, view, "angle", index)
        for index, payload in enumerate(frame_analysis.get("dashboard_candidates") or []):
            add(payload, payload.get("view") or "dashboard", "dashboard", index)
        for index, payload in enumerate(frame_analysis.get("representative_frames") or []):
            add(payload, payload.get("view") or "representative", "representative", index)

        return candidates

    def _index_vlm_frames(
        self,
        vlm_result: Dict[str, Any],
    ) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]]]:
        by_path: Dict[str, Dict[str, Any]] = {}
        by_view: Dict[str, Dict[str, Any]] = {}
        for entry in vlm_result.get("per_frame") or []:
            if not isinstance(entry, dict):
                continue
            if entry.get("frame"):
                by_path[_path_key(entry["frame"])] = entry
            view = canonical_section(entry.get("view") or entry.get("organizer_view"))
            if view and view != "needs-review":
                by_view.setdefault(view, entry)
        return by_path, by_view

    def _evidence_for(
        self,
        candidate: ImageCandidate,
        vlm_by_path: Dict[str, Dict[str, Any]],
        vlm_by_view: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        direct = vlm_by_path.get(_path_key(candidate.frame)) or {}
        if direct:
            return direct
        source_section = canonical_section(candidate.source_view)
        return vlm_by_view.get(source_section or "", {})

    def _labels_from_evidence(
        self,
        candidate: ImageCandidate,
        vlm_entry: Dict[str, Any],
        damage_frames: set[str],
    ) -> List[Tuple[str, float, str]]:
        labels: List[Tuple[str, float, str]] = []
        source_section = canonical_section(candidate.source_view)
        if source_section:
            score = candidate.organizer_score or (0.74 if candidate.high_confidence else 0.52)
            labels.append((source_section, score, "organizer"))

        vlm_section = canonical_section(vlm_entry.get("view") or vlm_entry.get("organizer_view"))
        if vlm_section:
            labels.append((vlm_section, 0.76, "vlm"))

        text_section = self._section_from_text(
            " ".join(
                str(vlm_entry.get(key) or "")
                for key in ("observations", "damage_notes", "notes")
            )
        )
        if text_section:
            labels.append((text_section, 0.66, "vlm_text"))

        if candidate.frame in damage_frames or _path_key(candidate.frame) in {_path_key(path) for path in damage_frames}:
            labels.append(("damage-closeups", 0.64, "damage_link"))

        return labels

    def _score_usability(self, candidate: ImageCandidate) -> Dict[str, Any]:
        reasons: List[str] = []
        section = canonical_section(candidate.source_view) or "needs-review"
        is_interior_or_detail = section in INTERIOR_SECTIONS or section in CLOSEUP_SECTIONS
        if candidate.quality_score < self.min_quality:
            reasons.append("low_quality")
        if (
            section in EXTERIOR_SECTIONS
            and candidate.vehicle_ratio < MIN_BACKGROUND_HEAVY_VEHICLE_RATIO
            and candidate.dashboard_score < 0.45
            and not candidate.high_confidence
        ):
            reasons.append("background_dominant")
        if section == "needs-review" and not is_interior_or_detail:
            reasons.append("unknown_section")
        return {
            "usable": len(reasons) == 0,
            "reasons": reasons,
            "quality_score": candidate.quality_score,
            "vehicle_ratio": candidate.vehicle_ratio,
            "foreground_bbox": candidate.foreground_bbox,
            "background_heavy": "background_dominant" in reasons,
        }

    def _route_candidate(
        self,
        candidate: ImageCandidate,
        vlm_entry: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], List[str]]:
        weighted: Dict[str, float] = {}
        sources: Dict[str, List[str]] = {}
        for section, confidence, source in candidate.labels:
            canonical = canonical_section(section)
            if not canonical:
                continue
            weighted[canonical] = max(weighted.get(canonical, 0.0), float(confidence or 0.0))
            sources.setdefault(canonical, []).append(source)

        section = "needs-review"
        confidence = 0.0
        if weighted:
            section, confidence = sorted(
                weighted.items(),
                key=lambda item: (item[1], item[0] == canonical_section(candidate.source_view)),
                reverse=True,
            )[0]

        source_section = canonical_section(candidate.source_view) or "needs-review"
        section, confidence, conflicts = self._resolve_section_conflicts(
            section,
            confidence,
            source_section,
            candidate,
            vlm_entry,
        )
        if source_section == "dashboard" and any(label in weighted for label in ("wheels", "tyres")):
            if "dashboard_cannot_classify_as_wheel_or_tyre" not in conflicts:
                conflicts.append("dashboard_cannot_classify_as_wheel_or_tyre")
            section = "dashboard"
            confidence = max(confidence, weighted.get("dashboard", 0.0), 0.65)
        if source_section in {"wheels", "tyres"} and any(label in weighted for label in INTERIOR_SECTIONS):
            conflict = f"{source_section}_cannot_classify_as_interior"
            if conflict not in conflicts:
                conflicts.append(conflict)
            section = source_section
            confidence = max(confidence, weighted.get(source_section, 0.0), 0.62)
        high_level = self._high_level_group(section)
        tags = sorted({section, high_level, *sources.get(section, [])})
        if candidate.usability.get("background_heavy"):
            tags.append("background-heavy")

        route = {
            "id": candidate.id,
            "frame": candidate.frame,
            "preview_path": candidate.preview_path or candidate.frame,
            "section": section,
            "group": high_level,
            "source_view": candidate.source_view,
            "confidence": round(float(confidence), 4),
            "quality_score": candidate.quality_score,
            "vehicle_ratio": candidate.vehicle_ratio,
            "foreground_bbox": candidate.foreground_bbox,
            "dashboard_score": candidate.dashboard_score,
            "timestamp_seconds": candidate.timestamp_seconds,
            "high_confidence": candidate.high_confidence or confidence >= MIN_STRONG_CONFIDENCE,
            "tags": tags,
            "validation": {
                "usable": candidate.usability.get("usable"),
                "reasons": candidate.usability.get("reasons") or [],
                "conflicts_resolved": conflicts,
            },
            "vlm_view": vlm_entry.get("view") if isinstance(vlm_entry, dict) else None,
        }
        return route, conflicts

    def _resolve_section_conflicts(
        self,
        section: str,
        confidence: float,
        source_section: str,
        candidate: ImageCandidate,
        vlm_entry: Dict[str, Any],
    ) -> Tuple[str, float, List[str]]:
        conflicts: List[str] = []
        text = " ".join(str(vlm_entry.get(key) or "") for key in ("observations", "damage_notes", "notes")).lower()

        if source_section in INTERIOR_SECTIONS and section in {"wheels", "tyres", "exhaust"}:
            conflicts.append(f"{section}_cannot_override_interior_{source_section}")
            return source_section, min(confidence, 0.58), conflicts

        if source_section in {"wheels", "tyres"} and section in INTERIOR_SECTIONS:
            conflicts.append(f"{source_section}_cannot_classify_as_interior")
            return source_section, max(confidence, 0.62), conflicts

        if source_section == "dashboard" and section in {"wheels", "tyres"}:
            conflicts.append("dashboard_cannot_classify_as_wheel_or_tyre")
            return "dashboard", max(confidence, 0.65), conflicts

        if section == "odometer" and source_section not in INTERIOR_SECTIONS:
            if "odometer" not in text and "instrument" not in text:
                conflicts.append("odometer_requires_dashboard_or_interior_context")
                return "dashboard", min(confidence, 0.55), conflicts

        if section == "steering-wheel" and source_section not in INTERIOR_SECTIONS:
            if "steering" not in text:
                conflicts.append("steering_wheel_requires_interior_context")
                return "seats", min(confidence, 0.54), conflicts

        if section == "exhaust" and source_section not in REAR_SECTIONS | {"exhaust"}:
            if "exhaust" not in text and "tailpipe" not in text and "muffler" not in text:
                conflicts.append("exhaust_requires_lower_rear_or_direct_exhaust_evidence")
                return source_section if source_section != "needs-review" else "damage-closeups", min(confidence, 0.52), conflicts

        if confidence < 0.35:
            conflicts.append("low_section_confidence")
            return "needs-review", confidence, conflicts

        return section, confidence, conflicts

    def _group_sections(self, images: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        sections = {section: [] for section in SECTION_ORDER}
        for image in images:
            section = image.get("section") if image.get("section") in sections else "needs-review"
            sections[section].append(image)
        for section, items in sections.items():
            items.sort(
                key=lambda item: (
                    -float(item.get("confidence") or 0.0),
                    -float(item.get("quality_score") or 0.0),
                    float(item.get("timestamp_seconds") or 999999.0),
                    str(item.get("frame") or ""),
                )
            )
            for position, item in enumerate(items):
                item["section_rank"] = position + 1
                item["primary"] = position == 0
        return sections

    def _resolve_duplicates(self, sections: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        best_by_frame: Dict[str, Dict[str, Any]] = {}
        duplicates: List[Dict[str, Any]] = []
        for section, items in sections.items():
            for item in items:
                frame_key = _path_key(item.get("frame"))
                current = best_by_frame.get(frame_key)
                if current is None or float(item.get("confidence") or 0.0) > float(current.get("confidence") or 0.0):
                    best_by_frame[frame_key] = item
        for section, items in sections.items():
            for item in items:
                best = best_by_frame.get(_path_key(item.get("frame")))
                if best is item:
                    continue
                item["duplicate_of_section"] = best.get("section")
                duplicates.append({
                    "frame": item.get("frame"),
                    "section": section,
                    "kept_section": best.get("section"),
                })
        return duplicates

    def _normalize_damage_items(self, damage: Dict[str, Any], vlm_result: Dict[str, Any]) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for location in damage.get("locations") or []:
            if not isinstance(location, dict):
                continue
            items.append(self._damage_item(location, "local_cv"))
        for item in vlm_result.get("damage_items") or []:
            if not isinstance(item, dict):
                continue
            items.append(self._damage_item(item, "vlm"))
        deduped: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
        for item in items:
            key = (
                item.get("type") or "damage",
                item.get("frame") or "",
                item.get("section") or item.get("location") or "",
            )
            current = deduped.get(key)
            if current is None or float(item.get("confidence") or 0.0) > float(current.get("confidence") or 0.0):
                deduped[key] = item
        return list(deduped.values())

    def _damage_item(self, source: Dict[str, Any], evidence_source: str) -> Dict[str, Any]:
        raw_type = str(source.get("type") or "damage").strip().lower().replace("_", " ")
        damage_type = DAMAGE_TYPE_ALIASES.get(raw_type, raw_type.replace(" ", "_") or "damage")
        section = canonical_section(source.get("organizer_view") or source.get("linked_view") or source.get("angle") or source.get("view"))
        return {
            "type": damage_type,
            "location": source.get("location") or source.get("notes") or "unknown",
            "section": section,
            "severity": source.get("severity") or "low",
            "confidence": _safe_float(source.get("confidence")),
            "frame": source.get("frame"),
            "bbox": source.get("bbox"),
            "source": evidence_source,
            "notes": source.get("notes"),
            "timestamp_seconds": source.get("timestamp_seconds"),
        }

    def _vehicle_payload(self, vehicle_info: Dict[str, Any], vlm_result: Dict[str, Any]) -> Dict[str, Any]:
        vlm_vehicle = vlm_result.get("vehicle") if isinstance(vlm_result.get("vehicle"), dict) else {}
        merged = {**vehicle_info, **{k: v for k, v in vlm_vehicle.items() if v not in (None, "")}}
        return {
            "manufacturer": merged.get("brand") or merged.get("manufacturer"),
            "model": merged.get("model"),
            "body_type": merged.get("body_type") or merged.get("vehicle_category") or merged.get("category") or merged.get("type"),
            "approximate_year": merged.get("year") or merged.get("year_range"),
            "variant": merged.get("variant") or merged.get("variant_candidate"),
            "color": merged.get("color"),
            "confidence": _safe_float(merged.get("confidence")),
            "source": merged.get("identity_source") or self._provider_name(vlm_result),
        }

    def _validation_summary(
        self,
        sections: Dict[str, List[Dict[str, Any]]],
        rejected_images: List[Dict[str, Any]],
        conflicts: List[str],
        duplicates: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        required = [section for section in CANONICAL_SECTIONS if section not in {"front-right", "needs-review"}]
        present = [section for section in required if sections.get(section)]
        missing = [section for section in required if section not in present]
        return {
            "passed": len(conflicts) == 0 and len(rejected_images) == 0,
            "present_sections": present,
            "missing_sections": missing,
            "conflicts_resolved": conflicts,
            "duplicates_resolved": duplicates,
            "rejected_count": len(rejected_images),
            "rules": [
                "dashboard_cannot_classify_as_wheel",
                "tyre_cannot_classify_as_interior",
                "exhaust_correlates_with_lower_rear",
                "odometer_correlates_with_dashboard_or_interior",
                "steering_wheel_correlates_with_interior",
                "low_confidence_or_background_heavy_routes_to_review",
            ],
        }

    def _section_from_text(self, text: str) -> Optional[str]:
        normalized = _normalize_label(text)
        for label, section in SECTION_ALIASES.items():
            if re.search(rf"\b{re.escape(label)}\b", normalized):
                return section
        return None

    def _high_level_group(self, section: str) -> str:
        if section in EXTERIOR_SECTIONS:
            return "exterior"
        if section in INTERIOR_SECTIONS:
            return "interior"
        if section in CLOSEUP_SECTIONS:
            return "closeup"
        return "review"

    def _count_groups(self, images: List[Dict[str, Any]]) -> Dict[str, int]:
        counts: Dict[str, int] = {"exterior": 0, "interior": 0, "closeup": 0, "review": 0}
        for item in images:
            counts[item.get("group") or "review"] = counts.get(item.get("group") or "review", 0) + 1
        return counts

    def _provider_name(self, vlm_result: Dict[str, Any]) -> str:
        if self.provider is not None:
            return getattr(self.provider, "name", "custom_vlm")
        return str(vlm_result.get("provider") or ("vlm" if vlm_result.get("available") else "heuristic_validation"))

    def _raw_model_payload(self, vlm_result: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "provider": vlm_result.get("provider"),
            "available": vlm_result.get("available"),
            "reason": vlm_result.get("reason"),
            "raw_summary": vlm_result.get("raw_summary"),
        }


def canonical_section(value: Any) -> Optional[str]:
    if value is None:
        return None
    normalized = _normalize_label(str(value))
    if not normalized:
        return None
    if normalized in CANONICAL_SECTIONS:
        return normalized
    return SECTION_ALIASES.get(normalized)


def _normalize_label(value: str) -> str:
    normalized = value.strip().lower().replace("_", " ").replace("/", " ")
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = normalized.replace(" - ", "-")
    if normalized in SECTION_ALIASES:
        return normalized
    return normalized.replace(" ", "-") if normalized.replace(" ", "-") in CANONICAL_SECTIONS else normalized


def _path_key(path: Any) -> str:
    if not isinstance(path, str):
        return ""
    return path.replace("\\", "/").split("uploads/")[-1]


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _safe_optional_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_bbox(value: Any) -> Optional[List[int]]:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    try:
        return [int(v) for v in value]
    except (TypeError, ValueError):
        return None


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default
