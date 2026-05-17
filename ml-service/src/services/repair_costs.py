"""
Repair cost estimation for damage locations.

Reads a tunable JSON rate card keyed by (part, type, severity) → {low, high}
and attaches per-location and aggregate cost estimates onto the damage dict.

The rate card path is configurable via ML_REPAIR_RATE_CARD_PATH. The default
ships at ml-service/src/config/repair_costs.json. Missing entries fall back
to type-only ranges; if even that misses, the location gets a null cost.
"""

from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def _default_path() -> str:
    here = Path(__file__).resolve().parent
    return str(here.parent / "config" / "repair_costs.json")


@lru_cache(maxsize=2)
def _load_rate_card(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        logger.warning("Repair rate card not found at %s; cost estimates disabled", path)
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as exc:
        logger.warning("Failed to parse repair rate card %s: %s", path, exc)
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def _rate_card() -> Dict[str, Any]:
    path = os.getenv("ML_REPAIR_RATE_CARD_PATH", "").strip() or _default_path()
    return _load_rate_card(path)


def _lookup_range(rate_card: Dict[str, Any], part: str, damage_type: str, severity: str) -> Optional[Tuple[float, float]]:
    by_part = rate_card.get("by_part_type_severity") or {}
    fallback = rate_card.get("fallback_by_type_severity") or {}

    part_entry = by_part.get(part) or {}
    type_entry = part_entry.get(damage_type) or {}
    range_entry = type_entry.get(severity)

    if not range_entry:
        # Try the type-only fallback.
        range_entry = (fallback.get(damage_type) or {}).get(severity)

    if not range_entry or not isinstance(range_entry, list) or len(range_entry) != 2:
        return None
    try:
        low = float(range_entry[0])
        high = float(range_entry[1])
    except (TypeError, ValueError):
        return None
    if high < low:
        low, high = high, low
    return low, high


def estimate_repair_costs(damage_data: Dict[str, Any]) -> None:
    """
    Mutate damage_data in-place:
    - Each location in damage_data["locations"] gets:
        estimated_cost: { low, high, midpoint, currency } or None
    - The top-level dict gets:
        total_estimated_repair_cost: { low, high, midpoint, currency, has_unknowns }
    """
    if not isinstance(damage_data, dict):
        return
    rate_card = _rate_card()
    currency = str(rate_card.get("currency") or "USD")
    locations = damage_data.get("locations") or []

    total_low = 0.0
    total_high = 0.0
    counted = 0
    unknowns = 0

    for loc in locations:
        if not isinstance(loc, dict):
            continue
        damage_type = str(loc.get("type") or "").lower()
        part = str(loc.get("part") or "unknown").lower()
        severity = str(loc.get("severity") or "medium").lower()
        if severity not in ("low", "medium", "high"):
            severity = "medium"

        cost_range = _lookup_range(rate_card, part, damage_type, severity)
        if cost_range is None:
            loc.setdefault("estimated_cost", None)
            unknowns += 1
            continue

        low, high = cost_range
        mid = (low + high) / 2.0
        loc.setdefault(
            "estimated_cost",
            {
                "low": round(low, 2),
                "high": round(high, 2),
                "midpoint": round(mid, 2),
                "currency": currency,
            },
        )
        total_low += low
        total_high += high
        counted += 1

    if counted == 0 and unknowns == 0:
        return

    damage_data["total_estimated_repair_cost"] = {
        "low": round(total_low, 2),
        "high": round(total_high, 2),
        "midpoint": round((total_low + total_high) / 2.0, 2),
        "currency": currency,
        "has_unknowns": unknowns > 0,
        "counted_locations": counted,
        "unknown_locations": unknowns,
    }
