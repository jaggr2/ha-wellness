"""Wellness integration."""

from __future__ import annotations

import logging
import os

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv, service

from .const import (
    ATTR_READING_ID,
    ATTR_USER,
    CONF_MOUNT_PATH,
    DOMAIN,
    SERVICE_ANALYZE_MEALS,
    SERVICE_ASSIGN_WEIGHT,
    SERVICE_DISMISS_WEIGHT,
    SERVICE_SAVE_BODY_METRICS,
)
from .coordinator import WellnessCoordinator
from .http import async_register_views

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.NUMBER, Platform.SENSOR, Platform.BUTTON]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Wellness from a config entry."""
    coordinator = WellnessCoordinator(hass, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    mount = entry.data.get(CONF_MOUNT_PATH, "")
    if not os.path.isdir(mount) or not os.access(mount, os.W_OK):
        _LOGGER.warning(
            "Wellness data folder %s is not writable — check the NAS mount "
            "(ledger writes will fail until it is restored)",
            mount,
        )

    await coordinator.async_load_pending()
    await coordinator.async_setup_weight_sensors()
    coordinator.async_setup_reminders()
    await coordinator.async_restore_meal_aggregates()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await _async_register_services(hass)
    await async_register_views(hass)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    coordinator: WellnessCoordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if coordinator is not None:
        coordinator.shutdown()
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when options/participants change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def _async_register_services(hass: HomeAssistant) -> None:
    """Register the Wellness services."""

    def _get_coordinator() -> WellnessCoordinator:
        entries = hass.data.get(DOMAIN, {})
        if not entries:
            raise HomeAssistantError("Wellness is not configured")
        return next(iter(entries.values()))

    async def _save_body_metrics(call: ServiceCall) -> None:
        coordinator = _get_coordinator()
        slug = call.data[ATTR_USER]
        if coordinator.get_participant(slug) is None:
            raise HomeAssistantError(f"No wellness participant with slug '{slug}'")
        await coordinator.save_body_metrics(slug)

    async def _assign_weight(call: ServiceCall) -> None:
        coordinator = _get_coordinator()
        await coordinator.async_assign_weight(call.data[ATTR_READING_ID], call.data[ATTR_USER])

    async def _dismiss_weight(call: ServiceCall) -> None:
        coordinator = _get_coordinator()
        await coordinator.async_dismiss_weight(call.data[ATTR_READING_ID])

    async def _analyze_meals(call: ServiceCall) -> None:
        coordinator = _get_coordinator()
        slug = call.data[ATTR_USER]
        if coordinator.get_participant(slug) is None:
            raise HomeAssistantError(f"No wellness participant with slug '{slug}'")
        await coordinator.analyze_meals(slug, limit=int(call.data.get("limit", 5)))

    service.async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_SAVE_BODY_METRICS,
        _save_body_metrics,
        schema=vol.Schema({vol.Required(ATTR_USER): cv.string}),
    )
    service.async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_ASSIGN_WEIGHT,
        _assign_weight,
        schema=vol.Schema(
            {vol.Required(ATTR_READING_ID): cv.string, vol.Required(ATTR_USER): cv.string}
        ),
    )
    service.async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_DISMISS_WEIGHT,
        _dismiss_weight,
        schema=vol.Schema({vol.Required(ATTR_READING_ID): cv.string}),
    )
    service.async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_ANALYZE_MEALS,
        _analyze_meals,
        schema=vol.Schema(
            {
                vol.Required(ATTR_USER): cv.string,
                vol.Optional("limit", default=5): cv.positive_int,
            }
        ),
    )
