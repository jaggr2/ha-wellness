"""Button platform — per-participant "save body metrics" action that appends
the current weight/waist to the JSONL ledger on the NAS mount."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SAVE_BUTTON_DEVICE_CLASS
from .coordinator import WellnessCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Wellness save-metrics buttons."""
    coordinator: WellnessCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        WellnessSaveButton(coordinator, entry, participant["slug"])
        for participant in coordinator.participants
    )


class WellnessSaveButton(ButtonEntity):
    """Append the user's current weight/waist to their body-metrics ledger."""

    def __init__(
        self,
        coordinator: WellnessCoordinator,
        entry: ConfigEntry,
        slug: str,
    ) -> None:
        super().__init__()
        self._coordinator = coordinator
        self._slug = slug
        self._attr_device_info = coordinator.device_info(slug)
        self._attr_unique_id = f"{entry.entry_id}_{slug}_save_metrics"
        self._attr_name = "Save body metrics"
        self._attr_has_entity_name = True
        self._attr_device_class = SAVE_BUTTON_DEVICE_CLASS
        self._attr_icon = "mdi:content-save-outline"

    async def async_press(self) -> None:
        """Save the current values to the ledger."""
        await self._coordinator.save_body_metrics(self._slug)
