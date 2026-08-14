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
