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
    CONF_MOUNT_PATH,
    DOMAIN,
    SERVICE_SAVE_BODY_METRICS,
)
from .coordinator import WellnessCoordinator

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

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await _async_register_services(hass)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when options/participants change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def _async_register_services(hass: HomeAssistant) -> None:
    """Register the save_body_metrics service."""

    async def _save_body_metrics(call: ServiceCall) -> None:
        slug = call.data["user"]
        for coordinator in hass.data.get(DOMAIN, {}).values():
            if coordinator.get_participant(slug):
                await coordinator.save_body_metrics(slug)
                return
        raise HomeAssistantError(f"No wellness participant with slug '{slug}'")

    service.async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_SAVE_BODY_METRICS,
        _save_body_metrics,
        schema=vol.Schema({vol.Required("user"): cv.string}),
    )
