from __future__ import annotations

from datetime import timedelta
from homeassistant.const import Platform

DOMAIN = "hassems"
PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.TEXT,
]

CONF_BASE_URL = "base_url"
CONF_TOKEN = "token"
CONF_WEBHOOK_ID = "webhook_id"
CONF_SUBSCRIPTION_ID = "subscription_id"
CONF_INCLUDED_HELPERS = "included_helpers"
CONF_IGNORED_HELPERS = "ignored_helpers"
DATA_HISTORY_CURSORS = "history_cursors"
HISTORICAL_WINDOW_DAYS = 10
DEFAULT_POLL_INTERVAL = timedelta(minutes=1)

SIGNAL_HELPER_ADDED = "hassems_helper_added_{entry_id}"
SIGNAL_HELPER_REMOVED = "hassems_helper_removed_{entry_id}"
SIGNAL_HELPER_UPDATED = "hassems_helper_updated_{entry_id}"

EVENT_HELPER_CREATED = "helper_created"
EVENT_HELPER_UPDATED = "helper_updated"
EVENT_HELPER_DELETED = "helper_deleted"
EVENT_HELPER_VALUE = "helper_value"

ATTR_HISTORY = "history"
ATTR_LAST_MEASURED = "last_measured_at"
ATTR_STATE_CLASS = "state_class"
ATTR_STATISTICS_MODE = "statistics_mode"
ATTR_HISTORY_CURSOR = "history_cursor"
ATTR_HISTORY_CURSOR_EVENTS = "history_cursor_events"
