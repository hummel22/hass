import sys
import types
from enum import Enum
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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

