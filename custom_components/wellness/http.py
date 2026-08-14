"""Authenticated HTTP views for the Wellness integration.

POST /api/wellness/photo  — multipart upload of a meal photo (authenticated).
The participant is resolved from the authenticated HA account, so each person
simply uses their own app account.
"""

from __future__ import annotations

from typing import Any

from aiohttp import web

from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PHOTO_EXTENSIONS, PHOTO_MAX_BYTES


def _get_coordinator(hass: HomeAssistant):
    entries = hass.data.get(DOMAIN, {})
    if not entries:
        return None
    return next(iter(entries.values()))


class WellnessPhotoView(HomeAssistantView):
    """Receive a meal photo and store it under the authenticated user's folder."""

    url = "/api/wellness/photo"
    name = "api:wellness:photo"
    requires_auth = True

    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        coordinator = _get_coordinator(hass)
        if coordinator is None:
            raise web.HTTPNotFound(text="Wellness is not configured")

        request._client_max_size = PHOTO_MAX_BYTES  # noqa: SLF001
        user = request.get("hass_user")
        if user is None:
            raise web.HTTPUnauthorized(text="Not authenticated")
        slug = coordinator.get_slug_for_user(user.id)
        if slug is None:
            raise web.HTTPForbidden(
                text=f"HA account '{user.name}' is not a wellness participant"
            )

        data = await request.post()
        field = data.get("file") or data.get("image")
        if field is None:
            raise web.HTTPBadRequest(text="Missing 'file' field")
        if field.content_type not in PHOTO_EXTENSIONS:
            raise web.HTTPBadRequest(
                text=f"Unsupported content type '{field.content_type}'"
            )

        photo = await coordinator.save_meal_photo(slug, field.file, field.content_type)
        return self.json({"ok": True, "user": slug, "photo": photo})


async def async_register_views(hass: HomeAssistant) -> None:
    hass.http.register_view(WellnessPhotoView())
