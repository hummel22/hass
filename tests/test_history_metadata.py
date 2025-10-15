from __future__ import annotations

import os
import sys
import asyncio
from datetime import datetime, timezone
from enum import Enum
from types import ModuleType, SimpleNamespace
from typing import Any, Dict, Generic, List, TypeVar
from unittest.mock import AsyncMock

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

if "aiohttp" not in sys.modules:
    aiohttp = ModuleType("aiohttp")

    class ClientError(Exception):
        pass

    class ClientResponse:
        def __init__(self, status: int = 200, *, content_type: str = "application/json") -> None:
            self.status = status
            self.content_type = content_type

        async def text(self) -> str:
            return ""

        async def json(self) -> Any:
            return {}

    class ClientSession:
        async def __aenter__(self) -> "ClientSession":
            return self

        async def __aexit__(self, *exc_info: Any) -> None:
            return None

        def request(self, *args: Any, **kwargs: Any):  # noqa: ANN401
            class _RequestContext:
                def __init__(self) -> None:
                    self._response = ClientResponse()

                async def __aenter__(self) -> ClientResponse:
                    return self._response

                async def __aexit__(self, *exc_info: Any) -> None:
                    return None

            return _RequestContext()

    aiohttp.ClientError = ClientError
    aiohttp.ClientResponse = ClientResponse
    aiohttp.ClientSession = ClientSession
    web_module = ModuleType("aiohttp.web")

    class Response:
        def __init__(self, *, status: int = 200) -> None:
            self.status = status

    web_module.Response = Response
    aiohttp.web = web_module
    sys.modules["aiohttp"] = aiohttp
    sys.modules["aiohttp.web"] = web_module


def _install_homeassistant_stubs() -> None:
    if "homeassistant" in sys.modules:
        return

    ha = ModuleType("homeassistant")
    sys.modules["homeassistant"] = ha

    # config entries stub
    config_entries = ModuleType("homeassistant.config_entries")

    class ConfigEntry:
        def __init__(
            self,
            *,
            data: Dict[str, Any] | None = None,
            options: Dict[str, Any] | None = None,
            entry_id: str = "test-entry",
        ) -> None:
            self.data = data or {}
            self.options = options or {}
            self.entry_id = entry_id

    config_entries.ConfigEntry = ConfigEntry
    config_entries.SOURCE_INTEGRATION_DISCOVERY = "integration_discovery"
    sys.modules["homeassistant.config_entries"] = config_entries
    ha.config_entries = config_entries

    # constants stub
    const = ModuleType("homeassistant.const")
    class Platform(str, Enum):
        SENSOR = "sensor"
        SWITCH = "switch"
        NUMBER = "number"
        SELECT = "select"
        TEXT = "text"

    const.Platform = Platform
    const.ATTR_DEVICE_CLASS = "device_class"
    const.CONF_TOKEN = "token"
    const.__version__ = "2024.0.0"
    const.ATTR_ENTITY_ID = "entity_id"
    const.ATTR_UNIT_OF_MEASUREMENT = "unit_of_measurement"
    const.EVENT_STATE_CHANGED = "state_changed"
    sys.modules["homeassistant.const"] = const
    ha.const = const

    # core stubs
    core = ModuleType("homeassistant.core")

    class Context:
        def __init__(self) -> None:
            self.id = "context-id"

    class Event:
        def __init__(
            self,
            event_type: str,
            data: Dict[str, Any],
            context: Context | None = None,
            origin: Any | None = None,
            time_fired_timestamp: float | None = None,
        ) -> None:
            self.event_type = event_type
            self.data = data
            self.context = context
            self.origin = origin
            self.time_fired_timestamp = time_fired_timestamp

    class EventOrigin:
        remote = "remote"

    class State:
        def __init__(
            self,
            entity_id: str,
            state: str,
            attributes: Dict[str, Any] | None = None,
            last_changed: datetime | None = None,
            last_updated: datetime | None = None,
            context: Context | None = None,
        ) -> None:
            self.entity_id = entity_id
            self.state = state
            self.attributes = attributes or {}
            self.last_changed = last_changed
            self.last_updated = last_updated
            self.context = context

    class HomeAssistant(SimpleNamespace):
        pass

    core.Context = Context
    core.Event = Event
    core.EventOrigin = EventOrigin
    core.HomeAssistant = HomeAssistant
    core.State = State
    sys.modules["homeassistant.core"] = core
    ha.core = core

    # exceptions stubs
    exceptions = ModuleType("homeassistant.exceptions")

    class HomeAssistantError(Exception):
        pass

    class ConfigEntryAuthFailed(HomeAssistantError):
        pass

    exceptions.HomeAssistantError = HomeAssistantError
    exceptions.ConfigEntryAuthFailed = ConfigEntryAuthFailed
    sys.modules["homeassistant.exceptions"] = exceptions
    ha.exceptions = exceptions

    # helpers dispatcher stub
    helpers = ModuleType("homeassistant.helpers")
    sys.modules["homeassistant.helpers"] = helpers

    dispatcher = ModuleType("homeassistant.helpers.dispatcher")

    def async_dispatcher_send(*_: Any, **__: Any) -> None:
        return None

    dispatcher.async_dispatcher_send = async_dispatcher_send
    dispatcher.async_dispatcher_connect = (
        lambda *args, **kwargs: (lambda: None)
    )
    sys.modules["homeassistant.helpers.dispatcher"] = dispatcher
    helpers.dispatcher = dispatcher

    aiohttp_client = ModuleType("homeassistant.helpers.aiohttp_client")

    async def async_get_clientsession(_: Any) -> Any:
        return ClientSession()

    aiohttp_client.async_get_clientsession = async_get_clientsession
    sys.modules["homeassistant.helpers.aiohttp_client"] = aiohttp_client
    helpers.aiohttp_client = aiohttp_client

    device_registry = ModuleType("homeassistant.helpers.device_registry")

    class DeviceInfo:
        def __init__(self, **kwargs: Any) -> None:
            self.__dict__.update(kwargs)

    device_registry.DeviceInfo = DeviceInfo
    sys.modules["homeassistant.helpers.device_registry"] = device_registry
    helpers.device_registry = device_registry

    # helpers update coordinator stub
    update_coordinator = ModuleType("homeassistant.helpers.update_coordinator")

    class UpdateFailed(Exception):
        pass

    T = TypeVar("T")

    class DataUpdateCoordinator(Generic[T]):
        def __init__(
            self,
            hass: HomeAssistant,
            logger: Any,
            *,
            name: str,
            update_interval: Any | None = None,
        ) -> None:
            self.hass = hass
            self.logger = logger
            self.name = name
            self.update_interval = update_interval
            self.data: T | None = None

        def async_set_updated_data(self, data: T) -> None:
            self.data = data

        async def async_request_refresh(self) -> None:
            return None

    class CoordinatorEntity(Generic[T]):
        def __init__(self, coordinator: DataUpdateCoordinator[T]) -> None:
            self.coordinator = coordinator
            self.hass = getattr(coordinator, "hass", None)

        async def async_added_to_hass(self) -> None:  # noqa: D401
            """Stub."""

        async def async_will_remove_from_hass(self) -> None:  # noqa: D401
            """Stub."""

    update_coordinator.UpdateFailed = UpdateFailed
    update_coordinator.DataUpdateCoordinator = DataUpdateCoordinator
    update_coordinator.CoordinatorEntity = CoordinatorEntity
    sys.modules["homeassistant.helpers.update_coordinator"] = update_coordinator
    helpers.update_coordinator = update_coordinator

    # components recorder stub
    components = ModuleType("homeassistant.components")
    sys.modules["homeassistant.components"] = components

    webhook = ModuleType("homeassistant.components.webhook")

    def _noop(*_: Any, **__: Any) -> None:
        return None

    webhook.async_generate_id = lambda: "webhook-id"
    webhook.async_register = _noop
    webhook.async_generate_url = lambda hass, webhook_id: f"https://example.test/{webhook_id}"
    webhook.async_unregister = _noop
    sys.modules["homeassistant.components.webhook"] = webhook
    components.webhook = webhook

    recorder = ModuleType("homeassistant.components.recorder")

    def get_instance(_: Any) -> Any:
        raise KeyError

    def is_entity_recorded(*_: Any) -> bool:
        return False

    recorder.get_instance = get_instance
    recorder.is_entity_recorded = is_entity_recorded
    sys.modules["homeassistant.components.recorder"] = recorder
    components.recorder = recorder

    statistics = ModuleType("homeassistant.components.recorder.statistics")
    statistics.StatisticData = Dict[str, Any]
    statistics.StatisticMeanType = float
    statistics.StatisticMetaData = Dict[str, Any]

    def async_add_external_statistics(*_: Any, **__: Any) -> None:
        return None

    def clear_statistics(*_: Any, **__: Any) -> None:
        return None

    statistics.async_add_external_statistics = async_add_external_statistics
    statistics.clear_statistics = clear_statistics
    sys.modules["homeassistant.components.recorder.statistics"] = statistics
    recorder.statistics = statistics

    # util.dt stub
    util = ModuleType("homeassistant.util")
    dt_module = ModuleType("homeassistant.util.dt")

    def parse_datetime(value: str | None) -> datetime | None:
        if value is None:
            return None
        value = value.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    def as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def as_timestamp(value: datetime) -> float:
        return value.timestamp()

    def utcnow() -> datetime:
        return datetime.now(timezone.utc)

    dt_module.parse_datetime = parse_datetime
    dt_module.as_utc = as_utc
    dt_module.as_timestamp = as_timestamp
    dt_module.utcnow = utcnow
    util.dt = dt_module
    sys.modules["homeassistant.util"] = util
    sys.modules["homeassistant.util.dt"] = dt_module
    ha.util = util


_install_homeassistant_stubs()

from custom_components.hassems import const
from custom_components.hassems.coordinator import HASSEMSCoordinator
from custom_components.hassems.entity import _format_history_for_diagnostics


def test_normalize_history_records_preserves_metadata() -> None:
    coordinator = object.__new__(HASSEMSCoordinator)

    entries = [
        {
            "measured_at": "2024-01-01T00:00:00+00:00",
            "value": 1,
            "history_cursor": "cursor-a",
            "historic": True,
            "historic_cursor": "historic-a",
        },
        {
            "measured_at": "2024-01-01T01:00:00+00:00",
            "value": 2,
        },
        {
            "measured_at": "2024-01-01T00:00:00+00:00",
            "value": 3,
            "history_cursor": "cursor-b",
            "historic": False,
            "historic_cursor": "historic-b",
        },
    ]

    normalized = coordinator._normalize_history_records(entries)

    assert normalized == [
        {
            "measured_at": "2024-01-01T00:00:00+00:00",
            "value": 3,
            "history_cursor": "cursor-b",
            "historic": False,
            "historic_cursor": "historic-b",
        },
        {
            "measured_at": "2024-01-01T01:00:00+00:00",
            "value": 2,
        },
    ]


def test_process_event_appends_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    coordinator = object.__new__(HASSEMSCoordinator)
    coordinator._helpers = {}
    coordinator._pending_discoveries = set()
    coordinator._history = {}
    coordinator._history_cursors = {}
    coordinator._history_cursors_dirty = False
    coordinator._included = set()
    coordinator._ignored = set()
    coordinator._recorded_measurements = {}
    coordinator._entity_ids = {}
    coordinator._async_store_measurements = AsyncMock()
    coordinator._async_process_history_cursor = AsyncMock()
    coordinator._save_history_cursors_if_needed = lambda: None
    coordinator._async_prompt_discovery = AsyncMock()
    coordinator.signal_update = "signal_update"
    coordinator.signal_add = "signal_add"
    coordinator.signal_remove = "signal_remove"
    coordinator.hass = SimpleNamespace()
    coordinator.data = {}

    def _set_updated_data(data: Dict[str, Any]) -> None:
        coordinator.data = data

    coordinator.async_set_updated_data = _set_updated_data  # type: ignore[assignment]

    dispatched: List[Dict[str, Any]] = []

    def _capture_dispatch(_hass: Any, signal: str, slug: str) -> None:
        dispatched.append({"signal": signal, "slug": slug})

    monkeypatch.setattr(
        "custom_components.hassems.coordinator.async_dispatcher_send",
        _capture_dispatch,
    )

    payload = {
        "helper": {
            "slug": "demo",
            "name": "Demo",
            "entity_type": "hassems",
        },
        "data": {
            "measured_at": "2024-01-01T02:00:00+00:00",
            "value": 42,
            "history_cursor": "cursor-value",
            "historic": True,
            "historic_cursor": "historic-value",
        },
    }

    asyncio.run(coordinator._async_process_event(const.EVENT_HELPER_VALUE, payload))

    history = coordinator._history.get("demo")
    assert history is not None
    assert history[-1] == {
        "value": 42,
        "measured_at": "2024-01-01T02:00:00+00:00",
        "history_cursor": "cursor-value",
        "historic": True,
        "historic_cursor": "historic-value",
    }
    assert coordinator.data.get("demo") == payload["helper"]
    assert dispatched[-1] == {"signal": coordinator.signal_add, "slug": "demo"}


def test_history_formatting_includes_metadata() -> None:
    history = [
        {
            "measured_at": "2024-01-01T03:00:00+00:00",
            "value": 5,
            "history_cursor": 123,
            "historic": False,
            "historic_cursor": "historic-cursor",
        }
    ]

    formatted = _format_history_for_diagnostics(history, limit=5)

    assert formatted == [
        {
            "measured_at": "2024-01-01T03:00:00+00:00",
            "value": 5,
            "history_cursor": "123",
            "historic": False,
            "historic_cursor": "historic-cursor",
        }
    ]

