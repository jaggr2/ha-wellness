"""Number platform — per-participant editable body weight and waist.

The number entity is the source of truth; the mirror sensor (sensor.py)
records the value to long-term statistics. Values persist across restarts
via RestoreNumber.
"""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode, RestoreNumber
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    WAIST_KIND,
    WAIST_MAX,
    WAIST_MIN,
    WAIST_STEP,
    WAIST_UNIT,
    WEIGHT_KIND,
    WEIGHT_MAX,
    WEIGHT_MIN,
    WEIGHT_STEP,
    WEIGHT_UNIT,
)
from .coordinator import WellnessCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Wellness number entities."""
    coordinator: WellnessCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []
    for participant in coordinator.participants:
        slug = participant["slug"]
        entities.append(WellnessNumber(coordinator, entry, slug, WEIGHT_KIND))
        entities.append(WellnessNumber(coordinator, entry, slug, WAIST_KIND))
    async_add_entities(entities)


class WellnessNumber(RestoreNumber):
    """Editable weight (kg) or waist (cm) for one participant."""

    def __init__(
        self,
        coordinator: WellnessCoordinator,
        entry: ConfigEntry,
        slug: str,
        kind: str,
    ) -> None:
        super().__init__()
        self._coordinator = coordinator
        self._slug = slug
        self._kind = kind
        self._attr_device_info = coordinator.device_info(slug)
        self._attr_unique_id = f"{entry.entry_id}_{slug}_{kind}"
        self._attr_has_entity_name = True
        self._attr_mode = NumberMode.BOX
        self._attr_native_value = coordinator.get_value(slug, kind)
        if kind == WEIGHT_KIND:
            self._attr_name = "Body weight"
            self._attr_native_unit_of_measurement = WEIGHT_UNIT
            self._attr_native_min_value = WEIGHT_MIN
            self._attr_native_max_value = WEIGHT_MAX
            self._attr_native_step = WEIGHT_STEP
        else:
            self._attr_name = "Waist"
            self._attr_native_unit_of_measurement = WAIST_UNIT
            self._attr_native_min_value = WAIST_MIN
            self._attr_native_max_value = WAIST_MAX
            self._attr_native_step = WAIST_STEP

    async def async_added_to_hass(self) -> None:
        """Restore the last value and push it to the coordinator."""
        await super().async_added_to_hass()
        last = await self.async_get_last_number_data()
        if last is not None and last.native_value is not None:
            value = float(last.native_value)
            self._attr_native_value = value
            self._coordinator.set_value(self._slug, self._kind, value)

    async def async_set_native_value(self, value: float) -> None:
        """Set the value (updates the coordinator, which mirrors to the sensor)."""
        value = float(value)
        self._attr_native_value = value
        self._coordinator.set_value(self._slug, self._kind, value)
        self.async_write_ha_state()
