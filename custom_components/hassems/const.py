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
CONF_INCLUDED_ENTITIES = "included_entities"
CONF_IGNORED_ENTITIES = "ignored_entities"
DATA_HISTORY_CURSORS = "history_cursors"
HISTORICAL_WINDOW_DAYS = 10
DEFAULT_POLL_INTERVAL = timedelta(minutes=1)

SIGNAL_ENTITY_ADDED = "hassems_entity_added_{entry_id}"
SIGNAL_ENTITY_REMOVED = "hassems_entity_removed_{entry_id}"
SIGNAL_ENTITY_UPDATED = "hassems_entity_updated_{entry_id}"

EVENT_ENTITY_CREATED = "entity_created"
EVENT_ENTITY_UPDATED = "entity_updated"
EVENT_ENTITY_DELETED = "entity_deleted"
EVENT_ENTITY_VALUE = "entity_value"

ATTR_HISTORY = "history"
ATTR_LAST_MEASURED = "last_measured_at"
ATTR_STATE_CLASS = "state_class"
ATTR_STATISTICS_MODE = "statistics_mode"
ATTR_HISTORY_CURSOR = "history_cursor"
ATTR_HISTORY_CURSOR_EVENTS = "history_cursor_events"
