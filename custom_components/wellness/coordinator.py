"""Shared coordinator for the Wellness integration.

Holds the resolved participants, the NAS mount path, and per-user metric
values shared between the editable `number` entities and the statistics
`sensor` entities (the number is the source of truth; sensors mirror it).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.util import dt as dt_util

from .const import (
    CONF_MOUNT_PATH,
    CONF_PARTICIPANTS,
    DEFAULT_MOUNT_PATH,
    DOMAIN,
    MANUFACTURER,
    MODEL,
    PARTICIPANT_NAME,
    PARTICIPANT_SLUG,
    WEIGHT_KIND,
)
from .ledger import append_body_metrics

type Listener = Callable[[], None]


class WellnessCoordinator:
    """Per-entry container for wellness state."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        # slug -> kind -> value (kg / cm)
        self._values: dict[str, dict[str, float]] = {}
        self._listeners: set[Listener] = set()

    # ------------------------------------------------------------------
    # Config accessors
    # ------------------------------------------------------------------
    @property
    def mount_path(self) -> Path:
        return Path(self.entry.data.get(CONF_MOUNT_PATH, DEFAULT_MOUNT_PATH))

    @property
    def participants(self) -> list[dict[str, Any]]:
        return self.entry.data.get(CONF_PARTICIPANTS, [])

    def get_participant(self, slug: str) -> dict[str, Any] | None:
        for participant in self.participants:
            if participant.get(PARTICIPANT_SLUG) == slug:
                return participant
        return None

    def participant_name(self, slug: str) -> str:
        participant = self.get_participant(slug)
        return (participant or {}).get(PARTICIPANT_NAME, slug.capitalize())

    def device_info(self, slug: str) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self.entry.entry_id}_{slug}")},
            name=self.participant_name(slug),
            manufacturer=MANUFACTURER,
            model=MODEL,
        )

    def ledger_path(self, slug: str, kind: str) -> Path:
        """Return the JSONL ledger path, e.g. mount/body-metrics-<slug>.jsonl."""
        return self.mount_path / f"{kind}-{slug}.jsonl"

    def photos_dir(self, slug: str) -> Path:
        return self.mount_path / "food-photos" / slug

    # ------------------------------------------------------------------
    # Metric values shared between number (source) and sensor (mirror)
    # ------------------------------------------------------------------
    def get_value(self, slug: str, kind: str) -> float | None:
        return self._values.get(slug, {}).get(kind)

    def set_value(self, slug: str, kind: str, value: float) -> None:
        self._values.setdefault(slug, {})[kind] = value
        self._notify_listeners()

    def add_listener(self, listener: Listener) -> None:
        self._listeners.add(listener)

    def remove_listener(self, listener: Listener) -> None:
        self._listeners.discard(listener)

    def _notify_listeners(self) -> None:
        for listener in list(self._listeners):
            listener()

    # ------------------------------------------------------------------
    # Body metrics
    # ------------------------------------------------------------------
    async def save_body_metrics(self, slug: str) -> bool:
        """Append the user's current weight/waist to their body-metrics ledger.

        Returns True if a row was written (deduped otherwise).
        """
        record = {
            "ts": dt_util.utcnow().isoformat(),
            "weight_kg": self.get_value(slug, WEIGHT_KIND),
            "waist_cm": self.get_value(slug, "waist"),
            "source": "manual",
        }
        path = str(self.ledger_path(slug, "body-metrics"))
        return await self.hass.async_add_executor_job(append_body_metrics, path, record)
