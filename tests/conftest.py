import asyncio
import inspect
import sys
import types
from contextlib import contextmanager
from datetime import datetime, timezone
from enum import Enum
from functools import wraps
from pathlib import Path
from typing import Any, Generic, TypeVar

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def pytest_configure(config: pytest.Config) -> None:  # pragma: no cover - test helper
    config.addinivalue_line(
        "markers",
        "asyncio: run the marked test inside an asyncio event loop",
    )


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:  # pragma: no cover
    for item in items:
        marker = item.get_closest_marker("asyncio")
        if marker is None:
            continue
        obj = item.obj
        if inspect.iscoroutinefunction(obj):
            @wraps(obj)
            def _wrapper(*args: Any, __obj=obj, **kwargs: Any):
                return asyncio.run(__obj(*args, **kwargs))

            item.obj = _wrapper

homeassistant_pkg = sys.modules.setdefault(
    "homeassistant",
    types.ModuleType("homeassistant"),
)
if not hasattr(homeassistant_pkg, "__path__"):
    homeassistant_pkg.__path__ = []

# homeassistant.config_entries
config_entries_module = types.ModuleType("homeassistant.config_entries")


class ConfigEntry:  # pragma: no cover - test stub
    def __init__(self) -> None:
        self.data = {}
        self.options = {}
        self.entry_id = ""


config_entries_module.ConfigEntry = ConfigEntry
homeassistant_pkg.config_entries = config_entries_module
sys.modules["homeassistant.config_entries"] = config_entries_module
sys.modules["homeassistant.config_entries"].ConfigEntry = ConfigEntry
homeassistant_pkg.config_entries = config_entries_module

# homeassistant.components
components_module = sys.modules.setdefault(
    "homeassistant.components",
    types.ModuleType("homeassistant.components"),
)
if not hasattr(components_module, "__path__"):
    components_module.__path__ = []
homeassistant_pkg.components = components_module

recorder_module = types.ModuleType("homeassistant.components.recorder")


def _recorder_not_implemented(*_args, **_kwargs):  # pragma: no cover - stub
    raise RuntimeError("recorder stub not configured")


recorder_module.get_instance = _recorder_not_implemented
recorder_module.is_entity_recorded = lambda *_args, **_kwargs: False

statistics_module = types.ModuleType("homeassistant.components.recorder.statistics")


class StatisticMeanType(Enum):
    ARITHMETIC = "arithmetic"


StatisticData = dict
StatisticMetaData = dict


def async_add_external_statistics(_hass, _metadata, _statistics):  # pragma: no cover - stub
    return None


def clear_statistics(_instance, _statistic_ids):  # pragma: no cover - stub
    return None


statistics_module.StatisticMeanType = StatisticMeanType
statistics_module.StatisticData = StatisticData
statistics_module.StatisticMetaData = StatisticMetaData
statistics_module.async_add_external_statistics = async_add_external_statistics
statistics_module.clear_statistics = clear_statistics

db_schema_module = types.ModuleType("homeassistant.components.recorder.db_schema")


class _RecorderModel:  # pragma: no cover - stub
    def __init__(self, *args, **kwargs) -> None:
        pass


db_schema_module.EventData = _RecorderModel
db_schema_module.Events = _RecorderModel
db_schema_module.EventTypes = _RecorderModel
db_schema_module.StateAttributes = _RecorderModel
db_schema_module.States = _RecorderModel
db_schema_module.StatesMeta = _RecorderModel


util_module = types.ModuleType("homeassistant.components.recorder.util")


@contextmanager
def session_scope(*_args, **_kwargs):  # pragma: no cover - stub
    yield None


util_module.session_scope = session_scope

recorder_module.statistics = statistics_module
recorder_module.db_schema = db_schema_module
recorder_module.util = util_module
components_module.recorder = recorder_module
sys.modules["homeassistant.components.recorder"] = recorder_module
sys.modules["homeassistant.components.recorder.statistics"] = statistics_module
sys.modules["homeassistant.components.recorder.db_schema"] = db_schema_module
sys.modules["homeassistant.components.recorder.util"] = util_module

# homeassistant.const
const_module = types.ModuleType("homeassistant.const")
const_module.ATTR_DEVICE_CLASS = "device_class"
const_module.ATTR_ENTITY_ID = "entity_id"
const_module.ATTR_UNIT_OF_MEASUREMENT = "unit_of_measurement"
const_module.EVENT_STATE_CHANGED = "state_changed"


class Platform(Enum):
    SENSOR = "sensor"
    SWITCH = "switch"
    NUMBER = "number"
    SELECT = "select"
    TEXT = "text"


const_module.Platform = Platform
homeassistant_pkg.const = const_module
sys.modules["homeassistant.const"] = const_module

# homeassistant.exceptions
exceptions_module = types.ModuleType("homeassistant.exceptions")


class HomeAssistantError(Exception):
    pass


class ConfigEntryAuthFailed(HomeAssistantError):
    pass


exceptions_module.HomeAssistantError = HomeAssistantError
exceptions_module.ConfigEntryAuthFailed = ConfigEntryAuthFailed
homeassistant_pkg.exceptions = exceptions_module
sys.modules["homeassistant.exceptions"] = exceptions_module

# homeassistant.core
core_module = types.ModuleType("homeassistant.core")


class _StateManager:  # pragma: no cover - stub
    def __init__(self) -> None:
        self._states: dict[str, Any] = {}

    def get(self, entity_id: str) -> Any:
        return self._states.get(entity_id)

    def set(self, entity_id: str, state: Any) -> None:
        self._states[entity_id] = state


class HomeAssistant:  # pragma: no cover - stub
    def __init__(self, _loop) -> None:
        self.data: dict[str, Any] = {}
        self.loop = _loop
        self.states = _StateManager()

    async def async_add_executor_job(self, func, *args, **kwargs):
        return func(*args, **kwargs)


core_module.HomeAssistant = HomeAssistant
homeassistant_pkg.core = core_module
sys.modules["homeassistant.core"] = core_module

# homeassistant.helpers
helpers_module = sys.modules.setdefault(
    "homeassistant.helpers",
    types.ModuleType("homeassistant.helpers"),
)
if not hasattr(helpers_module, "__path__"):
    helpers_module.__path__ = []

dispatcher_module = types.ModuleType("homeassistant.helpers.dispatcher")


def async_dispatcher_send(_hass, _signal, *_args, **_kwargs):  # pragma: no cover - stub
    return None


dispatcher_module.async_dispatcher_send = async_dispatcher_send
helpers_module.dispatcher = dispatcher_module
sys.modules["homeassistant.helpers.dispatcher"] = dispatcher_module

update_coordinator_module = types.ModuleType(
    "homeassistant.helpers.update_coordinator"
)


class UpdateFailed(Exception):
    pass


TData = TypeVar("TData")


class DataUpdateCoordinator(Generic[TData]):  # pragma: no cover - stub
    def __init__(self, hass, logger, *, name=None, update_interval=None) -> None:
        self.hass = hass
        self.logger = logger
        self.name = name
        self.update_interval = update_interval
        self.data: TData | None = None

    def async_set_updated_data(self, data: TData) -> None:
        self.data = data


update_coordinator_module.DataUpdateCoordinator = DataUpdateCoordinator
update_coordinator_module.UpdateFailed = UpdateFailed
helpers_module.update_coordinator = update_coordinator_module
sys.modules["homeassistant.helpers.update_coordinator"] = update_coordinator_module

# homeassistant.util.dt
util_pkg = sys.modules.setdefault(
    "homeassistant.util", types.ModuleType("homeassistant.util")
)
dt_module = types.ModuleType("homeassistant.util.dt")


def utcnow():  # pragma: no cover - stub
    return datetime.now(timezone.utc)


def as_utc(value):  # pragma: no cover - stub
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def parse_datetime(value):  # pragma: no cover - stub
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            if value.endswith("Z"):
                value = value[:-1] + "+00:00"
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


dt_module.utcnow = utcnow
dt_module.as_utc = as_utc
dt_module.parse_datetime = parse_datetime
dt_module.as_local = as_utc
dt_module.now = utcnow
util_pkg.dt = dt_module
homeassistant_pkg.util = util_pkg
sys.modules["homeassistant.util.dt"] = dt_module

custom_components_pkg = sys.modules.setdefault(
    "custom_components",
    types.ModuleType("custom_components"),
)
if not hasattr(custom_components_pkg, "__path__"):
    custom_components_pkg.__path__ = [str(ROOT / "custom_components")]

hassems_pkg = sys.modules.setdefault(
    "custom_components.hassems",
    types.ModuleType("custom_components.hassems"),
)
if not hasattr(hassems_pkg, "__path__"):
    hassems_pkg.__path__ = [str(ROOT / "custom_components" / "hassems")]

aiohttp_pkg = sys.modules.setdefault("aiohttp", types.ModuleType("aiohttp"))
if not hasattr(aiohttp_pkg, "web"):
    web_module = types.ModuleType("aiohttp.web")
    sys.modules["aiohttp.web"] = web_module
    aiohttp_pkg.web = web_module
if not hasattr(aiohttp_pkg, "ClientSession"):
    class _DummyClientSession:  # pragma: no cover - test stub only
        pass

    aiohttp_pkg.ClientSession = _DummyClientSession
if not hasattr(aiohttp_pkg, "ClientError"):
    aiohttp_pkg.ClientError = Exception
if not hasattr(aiohttp_pkg, "ClientResponse"):
    class _DummyClientResponse:  # pragma: no cover - test stub only
        pass

    aiohttp_pkg.ClientResponse = _DummyClientResponse
try:
    from homeassistant.components.recorder import statistics as recorder_statistics
except Exception:  # noqa: BLE001
    recorder_statistics = None
else:
    if not hasattr(recorder_statistics, "StatisticMeanType"):
        class StatisticMeanType(Enum):
            ARITHMETIC = "arithmetic"

        recorder_statistics.StatisticMeanType = StatisticMeanType
setattr(custom_components_pkg, "hassems", hassems_pkg)

