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
from homeassistant.components.sensor import SensorEntity, SensorStateClass

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
    entities.append(WellnessPendingSensor(coordinator, entry))
    for participant in coordinator.participants:
        slug = participant["slug"]
        entities.append(WellnessKcalSensor(coordinator, entry, slug))
        entities.append(WellnessLastMealSensor(coordinator, entry, slug))
        entities.append(WellnessMealStatusSensor(coordinator, entry, slug))
        entities.append(WellnessKcalRemainingSensor(coordinator, entry, slug))
        entities.append(WellnessEatingRegularitySensor(coordinator, entry, slug))
    async_add_entities(entities)


class WellnessKcalSensor(SensorEntity):
    """Today's estimated kcal from analyzed meals (Groq)."""

    def __init__(self, coordinator: WellnessCoordinator, entry: ConfigEntry, slug: str) -> None:
        super().__init__()
        self._coordinator = coordinator
        self._slug = slug
        self._attr_device_info = coordinator.device_info(slug)
        self._attr_unique_id = f"{entry.entry_id}_{slug}_today_kcal"
        self._attr_name = "Today kcal"
        self._attr_has_entity_name = True
        self._attr_native_unit_of_measurement = "kcal"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:fire"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._coordinator.add_listener(self._on_coordinator_update)
        self.async_on_remove(
            partial(self._coordinator.remove_listener, self._on_coordinator_update)
        )

    @callback
    def _on_coordinator_update(self) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self) -> float:
        return self._coordinator.today_kcal(self._slug)


class WellnessLastMealSensor(SensorEntity):
    """Description of the most recently analyzed meal."""

    def __init__(self, coordinator: WellnessCoordinator, entry: ConfigEntry, slug: str) -> None:
        super().__init__()
        self._coordinator = coordinator
        self._slug = slug
        self._attr_device_info = coordinator.device_info(slug)
        self._attr_unique_id = f"{entry.entry_id}_{slug}_last_meal"
        self._attr_name = "Last meal"
        self._attr_has_entity_name = True
        self._attr_icon = "mdi:food"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._coordinator.add_listener(self._on_coordinator_update)
        self.async_on_remove(
            partial(self._coordinator.remove_listener, self._on_coordinator_update)
        )

    @callback
    def _on_coordinator_update(self) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self) -> str:
        return self._coordinator.last_meal(self._slug)


class WellnessMealStatusSensor(SensorEntity):
    """Status of the latest Groq meal analysis (analyzing/done/error)."""

    def __init__(self, coordinator: WellnessCoordinator, entry: ConfigEntry, slug: str) -> None:
        super().__init__()
        self._coordinator = coordinator
        self._slug = slug
        self._attr_device_info = coordinator.device_info(slug)
        self._attr_unique_id = f"{entry.entry_id}_{slug}_meal_status"
        self._attr_name = "Meal analysis status"
        self._attr_has_entity_name = True
        self._attr_icon = "mdi:food-apple"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._coordinator.add_listener(self._on_coordinator_update)
        self.async_on_remove(
            partial(self._coordinator.remove_listener, self._on_coordinator_update)
        )

    @callback
    def _on_coordinator_update(self) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self) -> str:
        status = self._coordinator.meal_analysis_status(self._slug)
        return status.get("status", "idle")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return dict(self._coordinator.meal_analysis_status(self._slug))


class WellnessKcalRemainingSensor(SensorEntity):
    """Remaining kcal for the day vs the participant's daily target."""

    def __init__(self, coordinator: WellnessCoordinator, entry: ConfigEntry, slug: str) -> None:
        super().__init__()
        self._coordinator = coordinator
        self._slug = slug
        self._attr_device_info = coordinator.device_info(slug)
        self._attr_unique_id = f"{entry.entry_id}_{slug}_kcal_remaining"
        self._attr_name = "Kcal remaining"
        self._attr_has_entity_name = True
        self._attr_native_unit_of_measurement = "kcal"
        self._attr_icon = "mdi:chart-donut"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._coordinator.add_listener(self._on_coordinator_update)
        self.async_on_remove(
            partial(self._coordinator.remove_listener, self._on_coordinator_update)
        )

    @callback
    def _on_coordinator_update(self) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self) -> float:
        return self._coordinator.kcal_remaining(self._slug)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        target = self._coordinator.daily_kcal_target(self._slug)
        consumed = self._coordinator.today_kcal(self._slug)
        percent = round(consumed / target * 100, 1) if target else 0.0
        return {
            "target_kcal": target,
            "consumed_kcal": round(consumed, 1),
            "percent_consumed": percent,
        }


class WellnessEatingRegularitySensor(SensorEntity):
    """How often the participant eats today (count + gaps + too-frequent flag)."""

    def __init__(self, coordinator: WellnessCoordinator, entry: ConfigEntry, slug: str) -> None:
        super().__init__()
        self._coordinator = coordinator
        self._slug = slug
        self._attr_device_info = coordinator.device_info(slug)
        self._attr_unique_id = f"{entry.entry_id}_{slug}_eating_regularity"
        self._attr_name = "Meals today"
        self._attr_has_entity_name = True
        self._attr_icon = "mdi:silverware-fork-knife"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._coordinator.add_listener(self._on_coordinator_update)
        self.async_on_remove(
            partial(self._coordinator.remove_listener, self._on_coordinator_update)
        )

    @callback
    def _on_coordinator_update(self) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self) -> int:
        return self._coordinator.eating_regularity(self._slug)["meals_today"]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self._coordinator.eating_regularity(self._slug)


class WellnessPendingSensor(SensorEntity):
    """Count + details of unassigned smart-scale readings."""

    def __init__(self, coordinator: WellnessCoordinator, entry: ConfigEntry) -> None:
        super().__init__()
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_pending"
        self._attr_name = "Pending weight assignments"
        self._attr_has_entity_name = True
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_icon = "mdi:scale-bathroom"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._coordinator.add_listener(self._on_coordinator_update)
        self.async_on_remove(
            partial(self._coordinator.remove_listener, self._on_coordinator_update)
        )

    @callback
    def _on_coordinator_update(self) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self) -> int:
        return self._coordinator.pending_count

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"pending": self._coordinator.pending_list()}


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
