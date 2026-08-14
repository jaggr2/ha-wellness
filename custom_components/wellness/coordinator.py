"""Shared coordinator for the Wellness integration.

Holds the resolved participants, the NAS mount path, per-user metric values,
smart-scale assignment handling (pending readings, auto-assignment), meal
photo ingestion, and per-participant measurement reminders.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
import time
import uuid
from datetime import timedelta
from functools import partial
from pathlib import Path
from typing import Any, Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .analyzer import analyze_photo
from .assignment import find_assignee, should_ignore, to_kg
from .const import (
    ATTR_PHOTO,
    ATTR_READING_ID,
    ATTR_SENSOR_ID,
    ATTR_USER,
    ATTR_WEIGHT,
    CONF_GROQ_API_KEY,
    CONF_GROQ_MODEL,
    CONF_MOUNT_PATH,
    CONF_PARTICIPANTS,
    CONF_WEIGHT_SENSORS,
    DEFAULT_DAILY_KCAL_TARGET,
    DEFAULT_GROQ_MODEL,
    DEFAULT_MOUNT_PATH,
    DOMAIN,
    EVENT_MEASUREMENT_REMINDER,
    EVENT_MEAL_ANALYZED,
    EVENT_MEAL_DELETED,
    EVENT_MEAL_LOGGED,
    EVENT_PENDING_WEIGHT,
    EVENT_WEIGHT_ASSIGNED,
    MANUFACTURER,
    MODEL,
    PARTICIPANT_DAILY_KCAL_TARGET,
    PARTICIPANT_DAY_OF_WEEK,
    PARTICIPANT_HA_USER_ID,
    PARTICIPANT_INTERVAL_DAYS,
    PARTICIPANT_NAME,
    PARTICIPANT_SLUG,
    PARTICIPANT_TIME,
    PHOTO_EXTENSIONS,
    WEIGHT_KIND,
)
from .ledger import (
    append_body_metrics,
    append_jsonl,
    delete_photo,
    eating_regularity as _ledger_regularity,
    read_last_line,
    read_lines,
    read_photo,
    rewrite_jsonl,
    write_photo,
)

type Listener = Callable[[], None]

_LOGGER = logging.getLogger(__name__)


def _seconds_until_next(day_of_week: int, time_str: str) -> float:
    """Seconds until the next occurrence of (weekday, time) in local time."""
    now = dt_util.now()
    hour, minute = (int(p) for p in time_str.split(":"))
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    for offset in range(8):
        candidate = target + timedelta(days=offset)
        if candidate.weekday() == day_of_week and candidate > now:
            return (candidate - now).total_seconds()
    return 7 * 86400.0


class WellnessCoordinator:
    """Per-entry container for wellness state."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self._store = Store[dict[str, Any]](hass, 1, f"{DOMAIN}.pending")
        # slug -> kind -> value (kg / cm)
        self._values: dict[str, dict[str, float]] = {}
        self._listeners: set[Listener] = set()
        # pending scale readings: id -> record
        self._pending: dict[str, dict[str, Any]] = {}
        # per-sensor last handled reading for dedup: sensor_id -> (value, ts)
        self._last_weight: dict[str, tuple[float, float]] = {}
        # subscription / timer handles
        self._weight_unsub: Callable[[], None] | None = None
        self._reminder_unsubs: list[Callable[[], None]] = []
        self._daily_refresh_unsub: Callable[[], None] | None = None
        # per-user meal analysis aggregates
        self._today_kcal: dict[str, float] = {}
        self._last_meal: dict[str, str] = {}
        # latest analysis activity (for the status sensor): slug -> record
        self._analysis_status: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Config accessors
    # ------------------------------------------------------------------
    @property
    def mount_path(self) -> Path:
        return Path(self.entry.data.get(CONF_MOUNT_PATH, DEFAULT_MOUNT_PATH))

    @property
    def participants(self) -> list[dict[str, Any]]:
        return self.entry.data.get(CONF_PARTICIPANTS, [])

    @property
    def weight_sensors(self) -> list[str]:
        return self.entry.data.get(CONF_WEIGHT_SENSORS, [])

    def get_participant(self, slug: str) -> dict[str, Any] | None:
        for participant in self.participants:
            if participant.get(PARTICIPANT_SLUG) == slug:
                return participant
        return None

    def get_slug_for_user(self, user_id: str) -> str | None:
        for participant in self.participants:
            if participant.get(PARTICIPANT_HA_USER_ID) == user_id:
                return participant[PARTICIPANT_SLUG]
        return None

    def participant_name(self, slug: str) -> str:
        participant = self.get_participant(slug)
        return (participant or {}).get(PARTICIPANT_NAME, slug.capitalize())

    def device_info(self, slug: str) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self.entry.entry_id}_{slug}")},
            name=self.participant_name(slug),
            manufacturer=MANUFACTURER,
            model=MODEL,
        )

    def ledger_path(self, slug: str, kind: str) -> Path:
        """Return the JSONL ledger path, e.g. mount/body-metrics-<slug>.jsonl."""
        return self.mount_path / f"{kind}-{slug}.jsonl"

    def photos_dir(self, slug: str) -> Path:
        return self.mount_path / "food-photos" / slug

    # ------------------------------------------------------------------
    # Metric values shared between number (source) and sensor (mirror)
    # ------------------------------------------------------------------
    def get_value(self, slug: str, kind: str) -> float | None:
        return self._values.get(slug, {}).get(kind)

    def set_value(self, slug: str, kind: str, value: float) -> None:
        self._values.setdefault(slug, {})[kind] = value
        self._notify_listeners()

    def add_listener(self, listener: Listener) -> None:
        self._listeners.add(listener)

    def remove_listener(self, listener: Listener) -> None:
        self._listeners.discard(listener)

    def _notify_listeners(self) -> None:
        for listener in list(self._listeners):
            listener()

    # ------------------------------------------------------------------
    # Body metrics
    # ------------------------------------------------------------------
    async def save_body_metrics(self, slug: str) -> bool:
        """Append the user's current weight/waist to their body-metrics ledger."""
        record = {
            "ts": dt_util.utcnow().isoformat(),
            "weight_kg": self.get_value(slug, WEIGHT_KIND),
            "waist_cm": self.get_value(slug, "waist"),
            "source": "manual",
        }
        path = str(self.ledger_path(slug, "body-metrics"))
        return await self.hass.async_add_executor_job(append_body_metrics, path, record)

    async def _async_last_weight_history(self) -> dict[str, tuple[float | None, float | None]]:
        """Last logged weight per participant (from their ledger)."""
        history: dict[str, tuple[float | None, float | None]] = {}
        for participant in self.participants:
            slug = participant[PARTICIPANT_SLUG]
            last = await self.hass.async_add_executor_job(
                read_last_line, str(self.ledger_path(slug, "body-metrics"))
            )
            if last and last.get("weight_kg") is not None:
                ts: float | None = None
                if ts_str := last.get("ts"):
                    ts_dt = dt_util.parse_datetime(ts_str)
                    ts = ts_dt.timestamp() if ts_dt else None
                history[slug] = (float(last["weight_kg"]), ts)
        return history

    async def _async_log_scale_weight(
        self, slug: str, weight_kg: float, sensor_id: str, assigned_by: str
    ) -> None:
        record = {
            "ts": dt_util.utcnow().isoformat(),
            "weight_kg": weight_kg,
            "waist_cm": None,
            "source": "scale",
            "assigned_by": assigned_by,
            "sensor_id": sensor_id,
        }
        await self.hass.async_add_executor_job(
            append_jsonl, str(self.ledger_path(slug, "body-metrics")), record
        )
        self.set_value(slug, WEIGHT_KIND, weight_kg)
        self.hass.bus.async_fire(
            EVENT_WEIGHT_ASSIGNED,
            {ATTR_USER: slug, ATTR_WEIGHT: weight_kg, "assigned_by": assigned_by},
        )

    # ------------------------------------------------------------------
    # Smart-scale assignment
    # ------------------------------------------------------------------
    async def async_setup_weight_sensors(self) -> None:
        """Subscribe to the configured shared weight sensors."""
        sensors = self.weight_sensors
        if not sensors:
            return
        self._weight_unsub = async_track_state_change_event(
            self.hass, sensors, self._async_on_weight_change
        )

    @callback
    async def _async_on_weight_change(self, event: Event) -> None:
        new_state = event.data.get("new_state")
        if new_state is None or new_state.state in (None, "unknown", "unavailable"):
            return
        try:
            raw_value = float(new_state.state)
        except (TypeError, ValueError):
            return
        # Normalize to kg: scales may report g, lb, oz, etc.
        unit = new_state.attributes.get("unit_of_measurement")
        value = to_kg(raw_value, unit)
        sensor_id = new_state.entity_id
        now = time.time()
        last = self._last_weight.get(sensor_id)
        if should_ignore(value, *(last or (None, None))):
            return
        self._last_weight[sensor_id] = (value, now)

        history = await self._async_last_weight_history()
        result, target = find_assignee(value, history)
        if result == "assign":
            await self._async_log_scale_weight(target, value, sensor_id, assigned_by="auto")
            return

        reading_id = uuid.uuid4().hex
        self._pending[reading_id] = {
            "id": reading_id,
            "ts": dt_util.utcnow().isoformat(),
            ATTR_WEIGHT: value,
            ATTR_SENSOR_ID: sensor_id,
            "candidates": list(target),
        }
        await self._store.async_save(self._pending)
        self._notify_listeners()
        self.hass.bus.async_fire(
            EVENT_PENDING_WEIGHT,
            {
                ATTR_READING_ID: reading_id,
                ATTR_WEIGHT: value,
                ATTR_SENSOR_ID: sensor_id,
                "candidates": list(target),
            },
        )

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    def pending_list(self) -> list[dict[str, Any]]:
        participants = [
            {"slug": p[PARTICIPANT_SLUG], "name": p.get(PARTICIPANT_NAME, p[PARTICIPANT_SLUG])}
            for p in self.participants
        ]
        items = []
        for pid, pending in sorted(
            self._pending.items(), key=lambda kv: kv[1].get("ts", "")
        ):
            candidates = pending.get("candidates") or []
            items.append(
                {
                    "id": pid,
                    "ts": pending.get("ts"),
                    ATTR_WEIGHT: pending.get(ATTR_WEIGHT),
                    ATTR_SENSOR_ID: pending.get(ATTR_SENSOR_ID),
                    "candidates": [
                        {"slug": c, "name": self.participant_name(c)} for c in candidates
                    ],
                    "participants": participants,
                }
            )
        return items

    async def async_assign_weight(self, reading_id: str, slug: str) -> None:
        """Assign a pending reading to a participant."""
        pending = self._pending.get(reading_id)
        if pending is None:
            raise HomeAssistantError(f"No pending scale reading '{reading_id}'")
        if self.get_participant(slug) is None:
            raise HomeAssistantError(f"No wellness participant '{slug}'")
        await self._async_log_scale_weight(
            slug, pending[ATTR_WEIGHT], pending[ATTR_SENSOR_ID], assigned_by="manual"
        )
        self._pending.pop(reading_id, None)
        await self._store.async_save(self._pending)
        self._notify_listeners()

    async def async_dismiss_weight(self, reading_id: str) -> None:
        """Discard a pending scale reading."""
        if reading_id in self._pending:
            self._pending.pop(reading_id, None)
            await self._store.async_save(self._pending)
            self._notify_listeners()

    async def async_load_pending(self) -> None:
        data = await self._store.async_load()
        if isinstance(data, dict):
            self._pending = data

    # ------------------------------------------------------------------
    # Meal photos
    # ------------------------------------------------------------------
    async def save_meal_photo(
        self, slug: str, file_obj: Any, content_type: str
    ) -> str:
        """Store a meal photo and append a meal-log entry. Returns the photo path."""
        extension = PHOTO_EXTENSIONS[content_type]
        now_local = dt_util.now()
        rel_dir = (
            Path("food-photos")
            / slug
            / now_local.strftime("%Y")
            / now_local.strftime("%m")
            / now_local.strftime("%d")
        )
        filename = f"{now_local.strftime('%H%M%S')}_{secrets.token_hex(4)}.{extension}"
        abs_dir = self.mount_path / rel_dir
        abs_path = abs_dir / filename
        data = await self.hass.async_add_executor_job(file_obj.read)
        await self.hass.async_add_executor_job(
            write_photo, str(abs_dir), str(abs_path), data
        )
        record = {
            "ts": dt_util.utcnow().isoformat(),
            "photo": str(rel_dir / filename),
            "source": "ha-app",
        }
        await self.hass.async_add_executor_job(
            append_jsonl, str(self.ledger_path(slug, "meal-log")), record
        )
        self.hass.bus.async_fire(
            EVENT_MEAL_LOGGED,
            {ATTR_USER: slug, "photo": str(rel_dir / filename)},
        )
        # Kick off Groq analysis automatically so results show without a manual step.
        self.hass.async_create_task(self._async_auto_analyze_after_log(slug))
        return str(rel_dir / filename)

    async def _async_auto_analyze_after_log(self, slug: str) -> None:
        """Analyze the just-logged meal (latest photo only)."""
        await asyncio.sleep(2)
        try:
            await self.analyze_meals(slug, limit=1)
        except HomeAssistantError as err:
            _LOGGER.warning("Auto meal analysis skipped for %s: %s", slug, err)

    # ------------------------------------------------------------------
    # VLM meal analysis (Groq)
    # ------------------------------------------------------------------
    def _groq_credentials(self) -> tuple[str, str] | None:
        api_key = self.entry.data.get(CONF_GROQ_API_KEY)
        if not api_key:
            return None
        return api_key, self.entry.data.get(CONF_GROQ_MODEL, DEFAULT_GROQ_MODEL)

    async def analyze_meals(self, slug: str, limit: int = 5) -> int:
        """Analyze new meal photos for a participant with Groq vision.

        Returns the number of photos analyzed. Raises HomeAssistantError if
        no Groq API key is configured.
        """
        credentials = self._groq_credentials()
        if credentials is None:
            raise HomeAssistantError(
                "Groq API key not configured — add it in Wellness options"
            )
        api_key, model = credentials

        meals = await self.hass.async_add_executor_job(
            read_lines, str(self.ledger_path(slug, "meal-log"))
        )
        analyzed = {
            record.get("photo")
            for record in await self.hass.async_add_executor_job(
                read_lines, str(self.ledger_path(slug, "meal-analysis"))
            )
            if record.get("photo")
        }
        candidates = [m for m in meals if m.get("photo") and m["photo"] not in analyzed]
        candidates = candidates[-limit:]

        session = async_get_clientsession(self.hass)
        analyzed_count = 0
        for meal in candidates:
            photo_rel = meal["photo"]
            abs_path = self.mount_path / photo_rel
            self._set_analysis_status(
                slug,
                status="analyzing",
                photo=photo_rel,
                kcal=None,
                food=[],
            )
            try:
                photo_bytes = await self.hass.async_add_executor_job(
                    read_photo, str(abs_path)
                )
                analysis = await analyze_photo(session, api_key, model, photo_bytes)
            except (OSError, RuntimeError) as err:
                _LOGGER.warning(
                    "Meal analysis failed for %s/%s: %s", slug, photo_rel, err
                )
                self._set_analysis_status(slug, status="error", photo=photo_rel, error=str(err))
                continue
            await self.hass.async_add_executor_job(
                append_jsonl,
                str(self.ledger_path(slug, "meal-analysis")),
                {"ts": dt_util.utcnow().isoformat(), "photo": photo_rel, **analysis},
            )
            analyzed_count += 1
            await self._async_refresh_meal_aggregates(slug)
            self._set_analysis_status(
                slug,
                status="done",
                photo=photo_rel,
                kcal=analysis.get("estimated_kcal_total", 0),
                food=[f.get("item", "") for f in analysis.get("food", []) if f.get("item")],
            )
            self.hass.bus.async_fire(
                EVENT_MEAL_ANALYZED,
                {
                    ATTR_USER: slug,
                    "photo": photo_rel,
                    "estimated_kcal_total": analysis.get("estimated_kcal_total", 0),
                },
            )
        if not analyzed_count and candidates:
            self._set_analysis_status(slug, status="error", error="No photos could be analyzed")
        return analyzed_count

    def _set_analysis_status(self, slug: str, **attrs: Any) -> None:
        """Update the per-user meal analysis status and notify listeners."""
        self._analysis_status[slug] = attrs
        self._notify_listeners()

    def meal_analysis_status(self, slug: str) -> dict[str, Any]:
        """Return the latest analysis status record for a participant."""
        return self._analysis_status.get(slug, {})

    async def _async_refresh_meal_aggregates(self, slug: str) -> None:
        """Recompute today's kcal + last meal for a participant."""
        today = dt_util.now().date().isoformat()
        total = 0.0
        last_desc = ""
        for record in await self.hass.async_add_executor_job(
            read_lines, str(self.ledger_path(slug, "meal-analysis"))
        ):
            ts = record.get("ts", "")
            if ts.startswith(today):
                total += float(record.get("estimated_kcal_total", 0.0))
            if record.get("food") and not last_desc:
                items = [f.get("item", "") for f in record["food"] if f.get("item")]
                last_desc = ", ".join(items) or "meal"
        self._today_kcal[slug] = round(total, 1)
        self._last_meal[slug] = last_desc
        self._notify_listeners()

    def today_kcal(self, slug: str) -> float:
        return self._today_kcal.get(slug, 0.0)

    def last_meal(self, slug: str) -> str:
        return self._last_meal.get(slug, "—")

    async def async_restore_meal_aggregates(self) -> None:
        """Recompute today-kcal/last-meal from the analysis ledgers at startup."""
        for participant in self.participants:
            slug = participant[PARTICIPANT_SLUG]
            await self._async_refresh_meal_aggregates(slug)
        self._notify_listeners()

    # ------------------------------------------------------------------
    # Meal list / delete
    # ------------------------------------------------------------------
    def daily_kcal_target(self, slug: str) -> float:
        participant = self.get_participant(slug)
        return float(
            (participant or {}).get(PARTICIPANT_DAILY_KCAL_TARGET, DEFAULT_DAILY_KCAL_TARGET)
        )

    def kcal_remaining(self, slug: str) -> float:
        """Remaining kcal for the day (target minus consumed), never negative."""
        return max(0.0, self.daily_kcal_target(slug) - self.today_kcal(slug))

    async def async_list_meals(self, slug: str, limit: int = 20) -> list[dict[str, Any]]:
        """Return recent meals for a participant, newest first, merged with analysis."""
        meals = await self.hass.async_add_executor_job(
            read_lines, str(self.ledger_path(slug, "meal-log"))
        )
        analyses = await self.hass.async_add_executor_job(
            read_lines, str(self.ledger_path(slug, "meal-analysis"))
        )
        analysis_by_photo = {a.get("photo"): a for a in analyses if a.get("photo")}
        rows = []
        for meal in meals:
            photo = meal.get("photo")
            if not photo:
                continue
            row = {**meal, ATTR_PHOTO: photo}
            analysis = analysis_by_photo.get(photo)
            if analysis:
                row["food"] = [
                    f.get("item", "") for f in analysis.get("food", []) if f.get("item")
                ]
                row["estimated_kcal_total"] = analysis.get("estimated_kcal_total", 0)
            rows.append(row)
        rows.sort(key=lambda r: r.get("ts", ""), reverse=True)
        return rows[:limit]

    async def async_delete_meal(self, slug: str, photo: str) -> bool:
        """Delete a meal (photo + meal-log + meal-analysis entries). Returns True if removed."""
        photo = (photo or "").strip()
        if not photo:
            raise HomeAssistantError("Missing 'photo'")

        def _remove() -> tuple[int, int]:
            log_removed = rewrite_jsonl(
                str(self.ledger_path(slug, "meal-log")),
                lambda r: r.get("photo") != photo,
            )
            analysis_removed = rewrite_jsonl(
                str(self.ledger_path(slug, "meal-analysis")),
                lambda r: r.get("photo") != photo,
            )
            return log_removed, analysis_removed

        log_removed, analysis_removed = await self.hass.async_add_executor_job(_remove)
        if log_removed == 0:
            return False

        # Remove the photo file (best effort; already gone or missing is fine).
        abs_photo = self.mount_path / photo
        await self.hass.async_add_executor_job(delete_photo, str(abs_photo))

        # Drop any pending auto-analysis status for this photo.
        current = self._analysis_status.get(slug)
        if current and current.get(ATTR_PHOTO) == photo:
            self._analysis_status.pop(slug, None)

        await self._async_refresh_meal_aggregates(slug)
        self.hass.bus.async_fire(
            EVENT_MEAL_DELETED, {ATTR_USER: slug, ATTR_PHOTO: photo}
        )
        self._notify_listeners()
        return True

    # ------------------------------------------------------------------
    # Eating regularity
    # ------------------------------------------------------------------
    def _meal_times(self, slug: str) -> list[float]:
        """UTC epoch timestamps of logged meals for a participant, ascending."""
        records = read_lines(str(self.ledger_path(slug, "meal-log")))
        times: list[float] = []
        for record in records:
            ts_str = record.get("ts")
            if not ts_str:
                continue
            ts_dt = dt_util.parse_datetime(ts_str)
            if ts_dt is not None:
                times.append(ts_dt.timestamp())
        return sorted(times)

    def eating_regularity(self, slug: str) -> dict[str, Any]:
        """Stats about eating frequency for a participant."""
        result = _ledger_regularity(
            self._meal_times(slug),
            now=time.time(),
            today_start_epoch=dt_util.start_of_local_day(dt_util.now()).timestamp(),
        )
        # Add today's meal times as local HH:MM for the UI.
        today_start = dt_util.start_of_local_day(dt_util.now()).timestamp()
        today_times = [
            t
            for t in self._meal_times(slug)
            if t >= today_start and t <= time.time() + 60
        ]
        result["meal_times_today"] = [
            dt_util.as_local(dt_util.utc_from_timestamp(t)).strftime("%H:%M")
            for t in today_times
        ]
        return result

    # ------------------------------------------------------------------
    # Measurement reminders
    # ------------------------------------------------------------------
    def async_setup_reminders(self) -> None:
        for participant in self.participants:
            self._schedule_reminder(participant)

    def async_setup_daily_refresh(self) -> None:
        """Periodically re-notify so 'today' counters roll over at midnight."""
        self._daily_refresh_unsub = async_track_time_interval(
            self.hass,
            self._async_daily_refresh,
            timedelta(minutes=10),
        )

    @callback
    def _async_daily_refresh(self, _now) -> None:
        self._notify_listeners()

    def _schedule_reminder(self, participant: dict[str, Any]) -> None:
        slug = participant[PARTICIPANT_SLUG]
        interval_days = int(participant.get(PARTICIPANT_INTERVAL_DAYS, 7))
        day_of_week = int(participant.get(PARTICIPANT_DAY_OF_WEEK, 6))
        time_str = participant.get(PARTICIPANT_TIME, "20:00")
        delay = _seconds_until_next(day_of_week, time_str)
        unsub = async_call_later(
            self.hass,
            delay,
            partial(self._async_fire_reminder, slug, interval_days),
        )
        self._reminder_unsubs.append(unsub)

    async def _async_fire_reminder(self, slug: str, interval_days: int, _now) -> None:
        participant = self.get_participant(slug)
        if participant is not None:
            self.hass.bus.async_fire(
                EVENT_MEASUREMENT_REMINDER,
                {
                    ATTR_USER: slug,
                    "name": participant.get(PARTICIPANT_NAME, slug),
                    "interval_days": interval_days,
                },
            )
            self._schedule_reminder(participant)

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------
    def shutdown(self) -> None:
        if self._weight_unsub is not None:
            self._weight_unsub()
            self._weight_unsub = None
        for unsub in self._reminder_unsubs:
            unsub()
        self._reminder_unsubs.clear()
        if self._daily_refresh_unsub is not None:
            self._daily_refresh_unsub()
            self._daily_refresh_unsub = None
