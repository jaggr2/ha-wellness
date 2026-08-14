"""Constants for the Wellness integration."""

from homeassistant.components.button import ButtonDeviceClass
from homeassistant.components.number import NumberMode
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    UnitOfLength,
    UnitOfMass,
)

DOMAIN = "wellness"

PLATFORMS = ["number", "sensor", "button"]

CONF_MOUNT_PATH = "mount_path"
CONF_PARTICIPANTS = "participants"
CONF_WEIGHT_SENSORS = "weight_sensors"

PARTICIPANT_HA_USER_ID = "ha_user_id"
PARTICIPANT_NAME = "name"
PARTICIPANT_SLUG = "slug"
PARTICIPANT_INTERVAL_DAYS = "interval_days"
PARTICIPANT_DAY_OF_WEEK = "day_of_week"
PARTICIPANT_TIME = "time"

DEFAULT_MOUNT_PATH = "/share/wellness"
DEFAULT_INTERVAL_DAYS = 7
DEFAULT_DAY_OF_WEEK = 6  # Sunday (ISO weekday, Monday = 0)
DEFAULT_TIME = "20:00"

# Smart-scale assignment (Phase 2): assume a person's weight moved <= 5 kg.
MAX_DELTA_KG = 5.0
# Stale baselines (> 60 days) don't count as assignment candidates.
MAX_AGE_DAYS = 60

# Event names fired by the integration.
EVENT_MEASUREMENT_REMINDER = "wellness_measurement_reminder"
EVENT_PENDING_WEIGHT = "wellness_pending_weight"
EVENT_WEIGHT_ASSIGNED = "wellness_weight_assigned"

SERVICE_SAVE_BODY_METRICS = "save_body_metrics"
SERVICE_ASSIGN_WEIGHT = "assign_weight"
SERVICE_DISMISS_WEIGHT = "dismiss_weight"

ATTR_USER = "user"
ATTR_READING_ID = "reading_id"
ATTR_WEIGHT = "weight_kg"
ATTR_SENSOR_ID = "sensor_id"

# Supported meal-photo content types -> file extension.
PHOTO_EXTENSIONS = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
PHOTO_MAX_BYTES = 10 * 1024 * 1024

WEIGHT_KIND = "weight"
WAIST_KIND = "waist"

WEIGHT_UNIT = UnitOfMass.KILOGRAMS
WAIST_UNIT = UnitOfLength.CENTIMETERS

WEIGHT_MIN = 30.0
WEIGHT_MAX = 300.0
WEIGHT_STEP = 0.1
WAIST_MIN = 40.0
WAIST_MAX = 250.0
WAIST_STEP = 0.5

MANUFACTURER = "Home Assistant"
MODEL = "Wellness tracker"

SAVE_BUTTON_DEVICE_CLASS = ButtonDeviceClass.UPDATE

# device_class / unit / state_class per metric kind
METRIC_DEFS = {
    WEIGHT_KIND: {
        "name": "Body weight",
        "device_class": SensorDeviceClass.WEIGHT,
        "unit": WEIGHT_UNIT,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    WAIST_KIND: {
        "name": "Waist",
        "device_class": None,
        "unit": WAIST_UNIT,
        "state_class": SensorStateClass.MEASUREMENT,
    },
}
