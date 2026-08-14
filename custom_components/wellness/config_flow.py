"""Config flow for the Wellness integration."""

from __future__ import annotations

import os
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    CONF_GROQ_API_KEY,
    CONF_GROQ_MODEL,
    CONF_MOUNT_PATH,
    CONF_PARTICIPANTS,
    CONF_WEIGHT_SENSORS,
    DEFAULT_DAY_OF_WEEK,
    DEFAULT_GROQ_MODEL,
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
    """Real write test (more reliable than os.access as root)."""
    try:
        probe = os.path.join(path, ".wellness-write-probe")
        with open(probe, "w") as f:
            f.write("ok")
        os.remove(probe)
        return True
    except OSError:
        return False


async def _get_supervisor_mounts(hass: HomeAssistant) -> list[dict[str, Any]]:
    """Return configured supervisor mounts (name/user_path/usage/state)."""
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        return []
    session = async_get_clientsession(hass)
    try:
        async with session.get(
            "http://supervisor/mounts",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        ) as response:
            if response.status != 200:
                return []
            data = await response.json()
            return data.get("data", {}).get("mounts", [])
    except Exception:  # noqa: BLE001 — best effort
        return []


async def _mount_options(hass: HomeAssistant) -> list[dict[str, str]]:
    options = []
    for mount in await _get_supervisor_mounts(hass):
        name = mount.get("name")
        path = mount.get("user_path")
        if not name or not path:
            continue
        state = mount.get("state")
        label = f"{name} → {path}"
        if state and state != "active":
            label += f" ({state})"
        options.append({"value": path, "label": label})
    return options


async def _default_mount_path(hass: HomeAssistant) -> str:
    for mount in await _get_supervisor_mounts(hass):
        if mount.get("name") == "wellness" and mount.get("user_path"):
            return mount["user_path"]
        if mount.get("usage") == "share" and mount.get("user_path"):
            return mount["user_path"]
    return DEFAULT_MOUNT_PATH


async def _active_users(hass: HomeAssistant) -> list[Any]:
    """Return the non-system, active HA users."""
    users = await hass.auth.async_get_users()
    return [user for user in users if not user.system_generated and user.is_active]


async def _user_options(hass: HomeAssistant) -> list[dict[str, str]]:
    return [
        {"value": user.id, "label": user.name or user.id}
        for user in await _active_users(hass)
    ]


async def _users_by_id(hass: HomeAssistant) -> dict[str, str]:
    return {
        user.id: (user.name or "User")
        for user in await _active_users(hass)
    }


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
                users = await _users_by_id(self.hass)
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

        mount_options = await _mount_options(self.hass)
        default_mount = await _default_mount_path(self.hass)
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_MOUNT_PATH, default=default_mount
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=mount_options,
                        multiple=False,
                        custom_value=True,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(CONF_PARTICIPANTS): SelectSelector(
                    SelectSelectorConfig(
                        options=await _user_options(self.hass),
                        multiple=True,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
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
            # Route to the per-participant edit step when requested.
            if user_input.get("edit_slug"):
                self._edit_slug = user_input["edit_slug"]
                return await self.async_step_edit()

            if not _path_writable(user_input[CONF_MOUNT_PATH]):
                return self.async_show_form(
                    step_id="init",
                    data_schema=await self._build_schema(),
                    errors={CONF_MOUNT_PATH: "invalid_path"},
                )
            data = {**self._config_entry.data}
            data[CONF_MOUNT_PATH] = user_input[CONF_MOUNT_PATH]
            data[CONF_WEIGHT_SENSORS] = list(user_input.get("weight_sensors", []))
            if user_input.get(CONF_GROQ_API_KEY):
                data[CONF_GROQ_API_KEY] = user_input[CONF_GROQ_API_KEY]
            if user_input.get(CONF_GROQ_MODEL):
                data[CONF_GROQ_MODEL] = user_input[CONF_GROQ_MODEL]

            participants = list(data.get(CONF_PARTICIPANTS, []))
            slugs = {p[PARTICIPANT_SLUG] for p in participants}

            # remove
            for slug in user_input.get("remove_participants", []):
                participants = [p for p in participants if p[PARTICIPANT_SLUG] != slug]
                slugs.discard(slug)

            # add new users (not already participants)
            users = await _users_by_id(self.hass)
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

        return self.async_show_form(step_id="init", data_schema=await self._build_schema())

    async def async_step_edit(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        slug = getattr(self, "_edit_slug", None)
        data = self._config_entry.data
        participant = next(
            (p for p in data.get(CONF_PARTICIPANTS, []) if p[PARTICIPANT_SLUG] == slug),
            None,
        )
        if participant is None:
            return self.async_abort(reason="participant_not_found")

        if user_input is not None:
            normalized = {
                **user_input,
                PARTICIPANT_DAY_OF_WEEK: int(user_input[PARTICIPANT_DAY_OF_WEEK]),
                PARTICIPANT_INTERVAL_DAYS: int(user_input[PARTICIPANT_INTERVAL_DAYS]),
            }
            participants = [
                {**p, **normalized} if p[PARTICIPANT_SLUG] == slug else p
                for p in data.get(CONF_PARTICIPANTS, [])
            ]
            new_data = {**data, CONF_PARTICIPANTS: participants}
            self.hass.config_entries.async_update_entry(self._config_entry, data=new_data)
            return self.async_create_entry(title="", data={})

        schema = vol.Schema(
            {
                vol.Required(PARTICIPANT_NAME, default=participant.get(PARTICIPANT_NAME)): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.TEXT)
                ),
                vol.Required(
                    PARTICIPANT_INTERVAL_DAYS,
                    default=int(participant.get(PARTICIPANT_INTERVAL_DAYS, DEFAULT_INTERVAL_DAYS)),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=1,
                        max=90,
                        mode=NumberSelectorMode.BOX,
                        unit_of_measurement="days",
                    )
                ),
                vol.Required(
                    PARTICIPANT_DAY_OF_WEEK,
                    default=int(participant.get(PARTICIPANT_DAY_OF_WEEK, DEFAULT_DAY_OF_WEEK)),
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            {"value": "0", "label": "Monday"},
                            {"value": "1", "label": "Tuesday"},
                            {"value": "2", "label": "Wednesday"},
                            {"value": "3", "label": "Thursday"},
                            {"value": "4", "label": "Friday"},
                            {"value": "5", "label": "Saturday"},
                            {"value": "6", "label": "Sunday"},
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(
                    PARTICIPANT_TIME,
                    default=participant.get(PARTICIPANT_TIME, DEFAULT_TIME),
                ): TextSelector(TextSelectorConfig(type=TextSelectorType.TEXT)),
            }
        )
        return self.async_show_form(step_id="edit", data_schema=schema)

    async def _build_schema(self) -> vol.Schema:
        data = self._config_entry.data
        participants = data.get(CONF_PARTICIPANTS, [])
        participant_ids = {p[PARTICIPANT_HA_USER_ID] for p in participants}
        add_options = [
            {"value": user.id, "label": user.name or user.id}
            for user in await _active_users(self.hass)
            if user.id not in participant_ids
        ]
        remove_options = [
            {"value": p[PARTICIPANT_SLUG], "label": p[PARTICIPANT_NAME]}
            for p in participants
        ]
        edit_options = [
            {"value": p[PARTICIPANT_SLUG], "label": p[PARTICIPANT_NAME]}
            for p in participants
        ]
        mount_options = await _mount_options(self.hass)
        default_mount = await _default_mount_path(self.hass)
        return vol.Schema(
            {
                vol.Required(
                    CONF_MOUNT_PATH,
                    default=data.get(CONF_MOUNT_PATH, default_mount),
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=mount_options,
                        multiple=False,
                        custom_value=True,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional("add_users", default=[]): SelectSelector(
                    SelectSelectorConfig(
                        options=add_options,
                        multiple=True,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional("remove_participants", default=[]): SelectSelector(
                    SelectSelectorConfig(
                        options=remove_options,
                        multiple=True,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional("edit_slug", default=""): SelectSelector(
                    SelectSelectorConfig(
                        options=edit_options,
                        multiple=False,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    "weight_sensors",
                    default=data.get(CONF_WEIGHT_SENSORS, []),
                ): EntitySelector(EntitySelectorConfig(domain="sensor"), multiple=True),
                vol.Optional(
                    CONF_GROQ_API_KEY,
                    default=data.get(CONF_GROQ_API_KEY, ""),
                ): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
                vol.Optional(
                    CONF_GROQ_MODEL,
                    default=data.get(CONF_GROQ_MODEL, DEFAULT_GROQ_MODEL),
                ): TextSelector(TextSelectorConfig(type=TextSelectorType.TEXT)),
            }
        )
