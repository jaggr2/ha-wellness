"""Config flow for the Wellness integration."""

from __future__ import annotations

import os
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import HomeAssistant
from homeassistant.helpers.selector import (
    MultiSelectSelector,
    MultiSelectSelectorConfig,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    CONF_MOUNT_PATH,
    CONF_PARTICIPANTS,
    DEFAULT_DAY_OF_WEEK,
    DEFAULT_INTERVAL_DAYS,
    DEFAULT_MOUNT_PATH,
    DEFAULT_TIME,
    DOMAIN,
    PARTICIPANT_DAY_OF_WEEK,
    PARTICIPANT_HA_USER_ID,
    PARTICIPANT_INTERVAL_DAYS,
    PARTICIPANT_NAME,
    PARTICIPANT_SLUG,
    PARTICIPANT_TIME,
)
from .ledger import unique_slug


def _path_writable(path: str) -> bool:
    return os.path.isdir(path) and os.access(path, os.W_OK)


def _user_options(hass: HomeAssistant) -> list[dict[str, str]]:
    users = hass.auth.async_get_users()
    return [
        {"value": user.id, "label": user.name or user.id}
        for user in users
        if not user.system_generated and user.is_active
    ]


def _participant_from_user(user_id: str, name: str, existing_slugs: set[str]) -> dict[str, Any]:
    return {
        PARTICIPANT_HA_USER_ID: user_id,
        PARTICIPANT_NAME: name,
        PARTICIPANT_SLUG: unique_slug(name, existing_slugs),
        PARTICIPANT_INTERVAL_DAYS: DEFAULT_INTERVAL_DAYS,
        PARTICIPANT_DAY_OF_WEEK: DEFAULT_DAY_OF_WEEK,
        PARTICIPANT_TIME: DEFAULT_TIME,
    }


class WellnessConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the Wellness config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if not _path_writable(user_input[CONF_MOUNT_PATH]):
                errors[CONF_MOUNT_PATH] = "invalid_path"
            else:
                users = {user.id: (user.name or "User") for user in self.hass.auth.async_get_users()}
                participants = []
                slugs: set[str] = set()
                for user_id in user_input[CONF_PARTICIPANTS]:
                    participant = _participant_from_user(user_id, users[user_id], slugs)
                    slugs.add(participant[PARTICIPANT_SLUG])
                    participants.append(participant)
                return self.async_create_entry(
                    title="Wellness",
                    data={
                        CONF_MOUNT_PATH: user_input[CONF_MOUNT_PATH],
                        CONF_PARTICIPANTS: participants,
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_MOUNT_PATH, default=DEFAULT_MOUNT_PATH): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.TEXT)
                ),
                vol.Required(CONF_PARTICIPANTS): MultiSelectSelector(
                    MultiSelectSelectorConfig(options=_user_options(self.hass))
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return WellnessOptionsFlow(config_entry)


class WellnessOptionsFlow(OptionsFlow):
    """Handle options for the Wellness integration."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            if not _path_writable(user_input[CONF_MOUNT_PATH]):
                return self.async_show_form(
                    step_id="init",
                    data_schema=self._build_schema(),
                    errors={CONF_MOUNT_PATH: "invalid_path"},
                )
            data = {**self._config_entry.data}
            data[CONF_MOUNT_PATH] = user_input[CONF_MOUNT_PATH]

            participants = list(data.get(CONF_PARTICIPANTS, []))
            slugs = {p[PARTICIPANT_SLUG] for p in participants}

            # remove
            for slug in user_input.get("remove_participants", []):
                participants = [p for p in participants if p[PARTICIPANT_SLUG] != slug]
                slugs.discard(slug)

            # add new users (not already participants)
            users = {u.id: (u.name or "User") for u in self.hass.auth.async_get_users()}
            existing_ids = {p[PARTICIPANT_HA_USER_ID] for p in participants}
            for user_id in user_input.get("add_users", []):
                if user_id in existing_ids:
                    continue
                participant = _participant_from_user(user_id, users[user_id], slugs)
                slugs.add(participant[PARTICIPANT_SLUG])
                participants.append(participant)

            data[CONF_PARTICIPANTS] = participants
            self.hass.config_entries.async_update_entry(self._config_entry, data=data)
            return self.async_create_entry(title="", data={})

        return self.async_show_form(step_id="init", data_schema=self._build_schema())

    def _build_schema(self) -> vol.Schema:
        data = self._config_entry.data
        participants = data.get(CONF_PARTICIPANTS, [])
        participant_ids = {p[PARTICIPANT_HA_USER_ID] for p in participants}
        add_options = [
            {"value": u.id, "label": u.name or u.id}
            for u in self.hass.auth.async_get_users()
            if not u.system_generated and u.is_active and u.id not in participant_ids
        ]
        remove_options = [
            {"value": p[PARTICIPANT_SLUG], "label": p[PARTICIPANT_NAME]}
            for p in participants
        ]
        return vol.Schema(
            {
                vol.Required(
                    CONF_MOUNT_PATH,
                    default=data.get(CONF_MOUNT_PATH, DEFAULT_MOUNT_PATH),
                ): TextSelector(TextSelectorConfig(type=TextSelectorType.TEXT)),
                vol.Optional("add_users", default=[]): MultiSelectSelector(
                    MultiSelectSelectorConfig(options=add_options)
                ),
                vol.Optional("remove_participants", default=[]): MultiSelectSelector(
                    MultiSelectSelectorConfig(options=remove_options)
                ),
            }
        )
