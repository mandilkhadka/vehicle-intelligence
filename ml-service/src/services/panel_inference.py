"""
Panel taxonomy + part inference for damage locations.

Given the organized view a damage frame came from (front, rear-left, side, etc.)
and the bbox position within the vehicle bbox, infer the specific body panel
each damage location is on. Confidence reflects how strong the prior is — a
hit on a "front" frame in the centre-top is high-confidence hood; a hit on an
unknown view is low-confidence and falls back to a generic side panel.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# Canonical panel taxonomy. Kept flat so it's easy to lookup in the rate card.
PANEL_TAXONOMY: Tuple[str, ...] = (
    "front_bumper",
    "hood",
    "grille",
    "headlight_l",
    "headlight_r",
    "fender_l",
    "fender_r",
    "door_fl",
    "door_fr",
    "door_rl",
    "door_rr",
    "quarter_l",
    "quarter_r",
    "rocker_l",
    "rocker_r",
    "mirror_l",
    "mirror_r",
    "trunk",
    "tailgate",
    "rear_bumper",
    "taillight_l",
    "taillight_r",
    "roof",
    "windshield",
    "rear_window",
    "wheel_fl",
    "wheel_fr",
    "wheel_rl",
    "wheel_rr",
    "interior",
    "unknown",
)

# Human-readable labels for reports / UI.
PANEL_LABELS: Dict[str, str] = {
    "front_bumper": "Front bumper",
    "hood": "Hood",
    "grille": "Front grille",
    "headlight_l": "Left headlight",
    "headlight_r": "Right headlight",
    "fender_l": "Left front fender",
    "fender_r": "Right front fender",
    "door_fl": "Front-left door",
    "door_fr": "Front-right door",
    "door_rl": "Rear-left door",
    "door_rr": "Rear-right door",
    "quarter_l": "Left rear quarter panel",
    "quarter_r": "Right rear quarter panel",
    "rocker_l": "Left rocker panel",
    "rocker_r": "Right rocker panel",
    "mirror_l": "Left side mirror",
    "mirror_r": "Right side mirror",
    "trunk": "Trunk lid",
    "tailgate": "Tailgate",
    "rear_bumper": "Rear bumper",
    "taillight_l": "Left taillight",
    "taillight_r": "Right taillight",
    "roof": "Roof",
    "windshield": "Windshield",
    "rear_window": "Rear window",
    "wheel_fl": "Front-left wheel",
    "wheel_fr": "Front-right wheel",
    "wheel_rl": "Rear-left wheel",
    "wheel_rr": "Rear-right wheel",
    "interior": "Interior",
    "unknown": "Unknown area",
}


def panel_label(part: str) -> str:
    return PANEL_LABELS.get(part, part.replace("_", " ").title())


# Wheel/light damage types are part-determined regardless of bbox position.
_WHEEL_LIKE_TYPES = {"wheel_damage", "wheel"}
_LIGHT_LIKE_TYPES = {"broken_lights", "broken_light", "light_damage"}


def _bbox_thirds(bbox: List[float], vehicle_bbox: Optional[List[float]]) -> Tuple[str, str]:
    """
    Return (horizontal, vertical) thirds for the damage bbox within the
    vehicle bbox. Falls back to thirds-of-frame if vehicle_bbox is missing.

    horizontal: 'left' | 'centre' | 'right'
    vertical:   'top'  | 'middle' | 'bottom'
    """
    if not bbox or len(bbox) < 4:
        return "centre", "middle"

    cx = (float(bbox[0]) + float(bbox[2])) / 2.0
    cy = (float(bbox[1]) + float(bbox[3])) / 2.0

    if vehicle_bbox and len(vehicle_bbox) >= 4:
        vx1, vy1, vx2, vy2 = (float(v) for v in vehicle_bbox[:4])
        w = max(vx2 - vx1, 1.0)
        h = max(vy2 - vy1, 1.0)
        nx = (cx - vx1) / w
        ny = (cy - vy1) / h
    else:
        # No vehicle bbox; assume the bbox is already in vehicle-relative coords.
        # We can only normalise by the bbox itself which is not useful, so
        # default to centre/middle. Caller usually has the vehicle bbox.
        return "centre", "middle"

    if nx < 0.34:
        horiz = "left"
    elif nx < 0.66:
        horiz = "centre"
    else:
        horiz = "right"

    if ny < 0.34:
        vert = "top"
    elif ny < 0.66:
        vert = "middle"
    else:
        vert = "bottom"

    return horiz, vert


# View → ordered candidate panels by (horiz, vert) cell. Each list contains
# tuples (part, confidence). The first entry whose region matches is picked.
# Confidence values are deliberately modest because this is geometric prior
# only; a future fine-tuned model can override these.
_VIEW_RULES: Dict[str, Dict[Tuple[str, str], List[Tuple[str, float]]]] = {
    "front": {
        ("centre", "top"): [("hood", 0.7)],
        ("centre", "middle"): [("grille", 0.7)],
        ("centre", "bottom"): [("front_bumper", 0.75)],
        ("left", "top"): [("fender_l", 0.6)],
        ("right", "top"): [("fender_r", 0.6)],
        ("left", "middle"): [("headlight_l", 0.65)],
        ("right", "middle"): [("headlight_r", 0.65)],
        ("left", "bottom"): [("front_bumper", 0.65)],
        ("right", "bottom"): [("front_bumper", 0.65)],
    },
    "rear": {
        ("centre", "top"): [("roof", 0.5), ("rear_window", 0.4)],
        ("centre", "middle"): [("trunk", 0.6), ("tailgate", 0.6)],
        ("centre", "bottom"): [("rear_bumper", 0.75)],
        ("left", "middle"): [("taillight_l", 0.65)],
        ("right", "middle"): [("taillight_r", 0.65)],
        ("left", "bottom"): [("rear_bumper", 0.65)],
        ("right", "bottom"): [("rear_bumper", 0.65)],
    },
    "front-left": {
        ("left", "top"): [("fender_l", 0.55)],
        ("centre", "top"): [("hood", 0.55)],
        ("left", "middle"): [("door_fl", 0.6)],
        ("centre", "middle"): [("headlight_l", 0.55), ("grille", 0.5)],
        ("left", "bottom"): [("rocker_l", 0.55), ("wheel_fl", 0.45)],
        ("centre", "bottom"): [("front_bumper", 0.6)],
        ("right", "bottom"): [("front_bumper", 0.5)],
    },
    "front-right": {
        ("right", "top"): [("fender_r", 0.55)],
        ("centre", "top"): [("hood", 0.55)],
        ("right", "middle"): [("door_fr", 0.6)],
        ("centre", "middle"): [("headlight_r", 0.55), ("grille", 0.5)],
        ("right", "bottom"): [("rocker_r", 0.55), ("wheel_fr", 0.45)],
        ("centre", "bottom"): [("front_bumper", 0.6)],
        ("left", "bottom"): [("front_bumper", 0.5)],
    },
    "rear-left": {
        ("left", "top"): [("quarter_l", 0.6)],
        ("centre", "top"): [("roof", 0.4), ("rear_window", 0.4)],
        ("left", "middle"): [("door_rl", 0.6), ("quarter_l", 0.5)],
        ("centre", "middle"): [("trunk", 0.5), ("tailgate", 0.5)],
        ("left", "bottom"): [("rocker_l", 0.55), ("wheel_rl", 0.45)],
        ("centre", "bottom"): [("rear_bumper", 0.6)],
        ("right", "middle"): [("taillight_l", 0.55)],
    },
    "rear-right": {
        ("right", "top"): [("quarter_r", 0.6)],
        ("centre", "top"): [("roof", 0.4), ("rear_window", 0.4)],
        ("right", "middle"): [("door_rr", 0.6), ("quarter_r", 0.5)],
        ("centre", "middle"): [("trunk", 0.5), ("tailgate", 0.5)],
        ("right", "bottom"): [("rocker_r", 0.55), ("wheel_rr", 0.45)],
        ("centre", "bottom"): [("rear_bumper", 0.6)],
        ("left", "middle"): [("taillight_r", 0.55)],
    },
    "side-left": {
        ("left", "top"): [("roof", 0.4)],
        ("centre", "top"): [("roof", 0.4)],
        ("left", "middle"): [("door_fl", 0.45), ("door_rl", 0.45)],
        ("centre", "middle"): [("door_fl", 0.55)],
        ("right", "middle"): [("door_rl", 0.55)],
        ("left", "bottom"): [("rocker_l", 0.55), ("wheel_fl", 0.45)],
        ("right", "bottom"): [("rocker_l", 0.55), ("wheel_rl", 0.45)],
        ("centre", "bottom"): [("rocker_l", 0.6)],
    },
    "side-right": {
        ("left", "top"): [("roof", 0.4)],
        ("centre", "top"): [("roof", 0.4)],
        ("left", "middle"): [("door_fr", 0.45), ("door_rr", 0.45)],
        ("centre", "middle"): [("door_fr", 0.55)],
        ("right", "middle"): [("door_rr", 0.55)],
        ("left", "bottom"): [("rocker_r", 0.55), ("wheel_fr", 0.45)],
        ("right", "bottom"): [("rocker_r", 0.55), ("wheel_rr", 0.45)],
        ("centre", "bottom"): [("rocker_r", 0.6)],
    },
    "interior": {
        # Any interior frame; the bbox doesn't tell us much without a deeper
        # model so we lump everything as "interior" until we add cabin parts.
    },
    "dashboard": {},
}

# Some organizer view labels can arrive in slightly different shapes; this
# canonicalizes them.
_VIEW_ALIASES: Dict[str, str] = {
    "front_left": "front-left",
    "front-l": "front-left",
    "frontleft": "front-left",
    "front_right": "front-right",
    "front-r": "front-right",
    "frontright": "front-right",
    "rear_left": "rear-left",
    "rear-l": "rear-left",
    "rearleft": "rear-left",
    "rear_right": "rear-right",
    "rear-r": "rear-right",
    "rearright": "rear-right",
    "left": "side-left",
    "side_left": "side-left",
    "side-l": "side-left",
    "right": "side-right",
    "side_right": "side-right",
    "side-r": "side-right",
}


def _normalize_view(view: Optional[str]) -> Optional[str]:
    if not view:
        return None
    v = view.strip().lower()
    return _VIEW_ALIASES.get(v, v)


def infer_part(
    *,
    damage_type: Optional[str],
    bbox: Optional[List[float]],
    vehicle_bbox: Optional[List[float]],
    view: Optional[str],
) -> Tuple[str, float]:
    """
    Return (part, confidence). Confidence is in [0, 1]. Always returns a
    value — falls back to 'unknown' with 0.15 confidence so downstream code
    can rely on the field existing.
    """
    dtype = (damage_type or "").lower()

    # Type-determined overrides win regardless of view.
    if dtype in _WHEEL_LIKE_TYPES:
        side_part = _wheel_part_from_view(_normalize_view(view))
        return side_part or "wheel_fl", 0.55

    if dtype in _LIGHT_LIKE_TYPES:
        light_part = _light_part_from_view(_normalize_view(view))
        return light_part or "headlight_l", 0.55

    normalized_view = _normalize_view(view)
    if normalized_view == "interior" or normalized_view == "dashboard":
        return "interior", 0.4

    rules = _VIEW_RULES.get(normalized_view or "", {})
    horiz, vert = _bbox_thirds(bbox or [], vehicle_bbox)
    candidates = rules.get((horiz, vert))
    if candidates:
        part, conf = candidates[0]
        return part, float(conf)

    # No specific cell rule but we know the view family — pick a sensible
    # default panel for that view.
    if normalized_view in ("front",):
        return "front_bumper", 0.3
    if normalized_view in ("rear",):
        return "rear_bumper", 0.3
    if normalized_view in ("front-left", "side-left", "rear-left"):
        return "door_fl", 0.25
    if normalized_view in ("front-right", "side-right", "rear-right"):
        return "door_fr", 0.25

    return "unknown", 0.15


def _wheel_part_from_view(view: Optional[str]) -> Optional[str]:
    if not view:
        return None
    if "front-left" in view or view == "side-left":
        return "wheel_fl"
    if "front-right" in view or view == "side-right":
        return "wheel_fr"
    if "rear-left" in view:
        return "wheel_rl"
    if "rear-right" in view:
        return "wheel_rr"
    return None


def _light_part_from_view(view: Optional[str]) -> Optional[str]:
    if not view:
        return None
    if view.startswith("front"):
        return "headlight_l" if "left" in view else "headlight_r" if "right" in view else "headlight_l"
    if view.startswith("rear"):
        return "taillight_l" if "left" in view else "taillight_r" if "right" in view else "taillight_l"
    return None


def attach_parts_to_locations(
    locations: List[Dict[str, Any]],
    *,
    default_vehicle_bbox: Optional[List[float]] = None,
) -> None:
    """
    Mutate damage locations in-place to add `part` and `part_confidence`.

    Each location is expected to carry at minimum:
    - bbox: [x1, y1, x2, y2] in image coordinates
    - type: damage type string
    - angle / linked_view / view: organizer view label (any one of these)
    Optional:
    - vehicle_bbox: [x1, y1, x2, y2] of the vehicle within the frame.
    """
    for loc in locations:
        if not isinstance(loc, dict):
            continue
        view = loc.get("angle") or loc.get("linked_view") or loc.get("view")
        bbox = loc.get("bbox")
        vehicle_bbox = loc.get("vehicle_bbox") or default_vehicle_bbox
        part, conf = infer_part(
            damage_type=loc.get("type"),
            bbox=bbox if isinstance(bbox, list) else None,
            vehicle_bbox=vehicle_bbox if isinstance(vehicle_bbox, list) else None,
            view=view if isinstance(view, str) else None,
        )
        loc.setdefault("part", part)
        loc.setdefault("part_confidence", round(conf, 3))
        loc.setdefault("part_label", panel_label(part))
