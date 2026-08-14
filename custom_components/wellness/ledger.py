"""Pure JSONL ledger helpers (no HA imports — unit-testable)."""

from __future__ import annotations

import json
import os
import re
from typing import Any


def slugify(name: str) -> str:
    """Turn a display name into a safe entity slug ('Roger M.' -> 'roger_m')."""
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return slug or "user"


def unique_slug(name: str, existing: set[str]) -> str:
    """Return a slug for `name` that does not collide with `existing`."""
    base = slugify(name)
    slug = base
    counter = 2
    while slug in existing:
        slug = f"{base}_{counter}"
        counter += 1
    return slug


def append_jsonl(path: str, record: dict[str, Any]) -> None:
    """Append one JSON line to `path` (creating parent dirs)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_last_line(path: str) -> dict[str, Any] | None:
    """Read the last JSON line of `path`, or None if missing/invalid."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            line: str | None = None
            for line in f:
                pass
            if not line:
                return None
            return json.loads(line)
    except (FileNotFoundError, ValueError, OSError):
        return None


def read_lines(path: str) -> list[dict[str, Any]]:
    """Read all JSON lines of `path` (skipping malformed lines)."""
    records: list[dict[str, Any]] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except (json.JSONDecodeError, ValueError):
                    continue
    except (FileNotFoundError, OSError):
        pass
    return records


def read_photo(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def append_body_metrics(
    path: str, record: dict[str, Any], dedup: bool = True
) -> bool:
    """Append a body-metrics record; returns True if a row was written.

    With `dedup` (default), an exact duplicate of the last row (same values and
    source) is skipped so repeated Save presses don't create noise.
    """
    if dedup:
        last = read_last_line(path)
        if last is not None:
            same = all(last.get(k) == record.get(k) for k in ("weight_kg", "waist_cm", "source"))
            if same:
                return False
    append_jsonl(path, record)
    return True


def write_photo(directory: str, file_path: str, data: bytes) -> None:
    """Write photo bytes to disk, creating parent directories."""
    os.makedirs(directory, exist_ok=True)
    with open(file_path, "wb") as f:
        f.write(data)


def rewrite_jsonl(path: str, keep: Any) -> int:
    """Rewrite a JSONL file keeping only lines where keep(record) is True.

    Returns the number of records removed. Missing files are treated as empty.
    """
    records = read_lines(path)
    kept = [r for r in records if keep(r)]
    removed = len(records) - len(kept)
    if removed:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for record in kept:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return removed


def delete_photo(abs_path: str) -> bool:
    """Delete a photo file if it exists; returns True when removed."""
    try:
        os.remove(abs_path)
        return True
    except FileNotFoundError:
        return False


def eating_regularity(
    meal_times_epoch: list[float],
    now: float,
    today_start_epoch: float,
    min_gap_minutes: float = 120.0,
) -> dict[str, Any]:
    """Compute eating-frequency stats from meal timestamps (pure, testable).

    ``meal_times_epoch`` — ascending epoch timestamps of logged meals.
    Returns meal count today, min/avg/last gap (minutes) and a ``too_frequent``
    flag when consecutive meals are closer than ``min_gap_minutes``.
    """
    times = sorted(meal_times_epoch)
    today = [t for t in times if t >= today_start_epoch and t <= now + 60]

    gaps_s = [times[i] - times[i - 1] for i in range(1, len(times))]
    positive_gaps_min = [g / 60 for g in gaps_s if g > 0]
    min_gap_min = round(min(positive_gaps_min), 1) if positive_gaps_min else None
    avg_gap_min = (
        round(sum(positive_gaps_min) / len(positive_gaps_min), 1)
        if positive_gaps_min
        else None
    )
    last_gap_min = round(gaps_s[-1] / 60, 1) if gaps_s else None

    return {
        "meals_today": len(today),
        "min_gap_min": min_gap_min,
        "avg_gap_min": avg_gap_min,
        "last_gap_min": last_gap_min,
        "too_frequent": min_gap_min is not None and min_gap_min < min_gap_minutes,
    }
