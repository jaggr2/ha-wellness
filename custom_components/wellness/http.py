"""Authenticated HTTP views for the Wellness integration.

POST   /api/wellness/photo       — multipart upload of a meal photo (authenticated).
GET    /api/wellness/photo       — serve a stored meal photo (?path=...).
GET    /api/wellness/meals       — recent meals for the authenticated user.
POST   /api/wellness/meal/delete — delete a meal (?photo=...).
The participant is resolved from the authenticated HA account, so each person
simply uses their own app account.
"""

from __future__ import annotations

from pathlib import Path
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


def _resolve_user(hass: HomeAssistant, request: web.Request, coordinator):
    user = request.get("hass_user")
    if user is None:
        raise web.HTTPUnauthorized(text="Not authenticated")
    slug = coordinator.get_slug_for_user(user.id)
    if slug is None:
        raise web.HTTPForbidden(
            text=f"HA account '{user.name}' is not a wellness participant"
        )
    return slug


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
        slug = _resolve_user(hass, request, coordinator)

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


class WellnessMealsView(HomeAssistantView):
    """List recent meals for the authenticated user."""

    url = "/api/wellness/meals"
    name = "api:wellness:meals"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        coordinator = _get_coordinator(hass)
        if coordinator is None:
            raise web.HTTPNotFound(text="Wellness is not configured")

        slug = _resolve_user(hass, request, coordinator)
        limit = int(request.query.get("limit", "20"))
        meals = await coordinator.async_list_meals(slug, limit=limit)
        return self.json({"ok": True, "user": slug, "meals": meals})


class WellnessPhotoGetView(HomeAssistantView):
    """Serve a stored meal photo by relative path (?path=food-photos/...)."""

    url = "/api/wellness/photo"
    name = "api:wellness:photo:get"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        coordinator = _get_coordinator(hass)
        if coordinator is None:
            raise web.HTTPNotFound(text="Wellness is not configured")

        slug = _resolve_user(hass, request, coordinator)
        rel = request.query.get("path", "")
        rel = (rel or "").lstrip("/")
        if not rel or not rel.startswith("food-photos/"):
            raise web.HTTPBadRequest(text="Invalid path")

        abs_path = (coordinator.mount_path / rel).resolve()
        mount = coordinator.mount_path.resolve()
        if not abs_path.is_relative_to(mount) or not abs_path.is_file():
            raise web.HTTPNotFound(text="Photo not found")

        return web.FileResponse(abs_path)


class WellnessMealDeleteView(HomeAssistantView):
    """Delete a logged meal for the authenticated user."""

    url = "/api/wellness/meal/delete"
    name = "api:wellness:meal:delete"
    requires_auth = True

    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        coordinator = _get_coordinator(hass)
        if coordinator is None:
            raise web.HTTPNotFound(text="Wellness is not configured")

        slug = _resolve_user(hass, request, coordinator)
        data = await request.json()
        photo = data.get("photo")
        if not photo:
            raise web.HTTPBadRequest(text="Missing 'photo'")

        removed = await coordinator.async_delete_meal(slug, photo)
        if not removed:
            raise web.HTTPNotFound(text="Meal not found")
        return self.json({"ok": True, "removed": True})


async def async_register_views(hass: HomeAssistant) -> None:
    hass.http.register_view(WellnessPhotoView())
    hass.http.register_view(WellnessPhotoGetView())
    hass.http.register_view(WellnessMealsView())
    hass.http.register_view(WellnessMealDeleteView())
