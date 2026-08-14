"""Sensor platform — mirrors the per-participant number values into
state_class=measurement sensors so Home Assistant records long-term
statistics (trend charts)."""

from __future__ import annotations

from functools import partial
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import Entity
from homeassistant.components.sensor import SensorEntity

from .const import DOMAIN, METRIC_DEFS, WEIGHT_KIND
from .coordinator import WellnessCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Wellness sensor entities."""
    coordinator: WellnessCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []
    for participant in coordinator.participants:
        slug = participant["slug"]
        for kind in METRIC_DEFS:
            entities.append(WellnessMetricSensor(coordinator, entry, slug, kind))
    async_add_entities(entities)


class WellnessMetricSensor(SensorEntity):
    """Statistics mirror of a participant's weight or waist number."""

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
        definition = METRIC_DEFS[kind]
        self._attr_device_info = coordinator.device_info(slug)
        self._attr_unique_id = f"{entry.entry_id}_{slug}_{kind}_statistics"
        self._attr_has_entity_name = True
        self._attr_name = f"{definition['name']} (statistics)"
        self._attr_device_class = definition["device_class"]
        self._attr_native_unit_of_measurement = definition["unit"]
        self._attr_state_class = definition["state_class"]
        if kind != WEIGHT_KIND:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

    async def async_added_to_hass(self) -> None:
        """Subscribe to coordinator value changes."""
        await super().async_added_to_hass()
        self._coordinator.add_listener(self._on_coordinator_update)
        self.async_on_remove(
            partial(self._coordinator.remove_listener, self._on_coordinator_update)
        )

    @callback
    def _on_coordinator_update(self) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self) -> Any:
        return self._coordinator.get_value(self._slug, self._kind)
