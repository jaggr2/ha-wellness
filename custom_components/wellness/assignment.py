"""Pure smart-scale assignment helpers (no HA imports — unit-testable).

Assignment rule: a shared-scale reading is assigned to a participant whose
last logged weight is recent (within ``max_age_days``) and within
``max_delta`` kg of the reading. Exactly one such candidate -> assign;
otherwise the reading must be disambiguated by a human (ask).
"""

from __future__ import annotations

import time
from typing import Any

# {slug: (last_weight_kg, last_ts_epoch)}
WeightHistory = dict[str, tuple[float | None, float | None]]

# Mass units (lowercase, without whitespace) -> kg factor.
_UNIT_TO_KG: dict[str, float] = {
    "g": 0.001,
    "kg": 1.0,
    "lb": 0.45359237,
    "lbs": 0.45359237,
    "oz": 0.028349523125,
    "st": 6.35029318,
    "stone": 6.35029318,
}


def to_kg(value: float, unit: str | None) -> float:
    """Convert a weight reading to kg given its unit_of_measurement."""
    if not unit:
        return value
    factor = _UNIT_TO_KG.get(unit.strip().lower())
    return value * factor if factor is not None else value


def should_ignore(
    value: float,
    last_value: float | None,
    last_ts: float | None,
    min_delta: float = 0.1,
    min_interval_s: float = 300,
    now: float | None = None,
) -> bool:
    """Ignore repeated/redundant scale pushes (same value within a window)."""
    if last_value is None or last_ts is None:
        return False
    now = time.time() if now is None else now
    if abs(value - last_value) < min_delta and (now - last_ts) < min_interval_s:
        return True
    return False


def find_assignee(
    weight_kg: float,
    history: WeightHistory,
    max_delta: float = 5.0,
    max_age_days: float = 60.0,
    now: float | None = None,
) -> tuple[str, Any]:
    """Return ("assign", slug) when unambiguous, else ("ask", candidates).

    Candidates are participant slugs whose last weight is within
    ``max_age_days`` and ``max_delta`` of the reading. Zero or multiple
    candidates -> ask.
    """
    now = time.time() if now is None else now
    candidates: list[str] = []
    for slug, (last_weight, last_ts) in history.items():
        if last_weight is None or last_ts is None:
            continue
        if (now - last_ts) / 86400.0 > max_age_days:
            continue
        if abs(weight_kg - last_weight) <= max_delta:
            candidates.append(slug)
    if len(candidates) == 1:
        return "assign", candidates[0]
    return "ask", candidates
