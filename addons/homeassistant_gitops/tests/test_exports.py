import asyncio
import importlib.machinery
import importlib.util
import json
import os
import sys
import uuid
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

REPO_ROOT = Path(__file__).resolve().parents[3]
APP_PATH = REPO_ROOT / "addons/homeassistant_gitops/rootfs/app/main.py"


def load_main(tmp_path: Path):
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    options_path = tmp_path / "options.json"
    options_path.write_text(json.dumps({"yaml_modules_enabled": True}), encoding="utf-8")

    os.environ["HASS_CONFIG_DIR"] = str(config_dir)
    os.environ["HASS_OPTIONS_PATH"] = str(options_path)

    for module_name in list(sys.modules):
        if module_name.startswith("gitops_bridge"):
            sys.modules.pop(module_name, None)

    module_name = f"ha_gitops_main_{uuid.uuid4().hex}"
    loader = importlib.machinery.SourceFileLoader(module_name, str(APP_PATH))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module, config_dir


def get_exports_module():
    return sys.modules["gitops_bridge.exports"]


def read_csv_rows(path: Path):
    import csv

    content = path.read_text(encoding="utf-8")
    reader = csv.reader(content.splitlines())
    return list(reader)


def test_exports_config_round_trip(tmp_path: Path) -> None:
    load_main(tmp_path)
    exports = get_exports_module()

    saved = exports.save_exports_config(
        {"schema_version": 1, "entities": {"integration_blacklist": ["Demo", " demo "]}}
    )
    assert saved["entities"]["integration_blacklist"] == ["demo"]

    loaded = exports.load_exports_config()
    assert loaded["entities"]["integration_blacklist"] == ["demo"]


def test_export_entities_writes_csv_and_filters_blacklist(tmp_path: Path, monkeypatch) -> None:
    _, config_dir = load_main(tmp_path)
    exports = get_exports_module()
    exports.save_exports_config(
        {"schema_version": 1, "entities": {"integration_blacklist": ["demo"]}}
    )

    async def fake_get(path: str):
        if path == "/config/area_registry":
            return [{"area_id": "area-1", "name": "Kitchen", "floor": "1"}]
        if path == "/config/device_registry":
            return [
                {
                    "id": "device-1",
                    "name": "Main device",
                    "area_id": "area-1",
                }
            ]
        if path == "/config/entity_registry":
            return [
                {
                    "entity_id": "light.kitchen",
                    "name": "Kitchen light",
                    "platform": "demo",
                    "device_id": "device-1",
                },
                {
                    "entity_id": "switch.fan",
                    "name": "Fan",
                    "platform": "other",
                    "device_id": "device-1",
                },
            ]
        raise AssertionError("Unexpected path")

    monkeypatch.setattr(exports, "_ha_get_json", fake_get)

    asyncio.run(exports.run_export("entities"))

    csv_path = config_dir / "system/entities.csv"
    rows = read_csv_rows(csv_path)
    headers = rows[0]
    assert "device_name" in headers
    assert any(row[0] == "switch.fan" for row in rows[1:])
    assert not any(row[0] == "light.kitchen" for row in rows[1:])


def test_export_devices_writes_csv(tmp_path: Path, monkeypatch) -> None:
    _, config_dir = load_main(tmp_path)
    exports = get_exports_module()

    async def fake_get(path: str):
        if path == "/config/area_registry":
            return [{"area_id": "area-1", "name": "Office"}]
        if path == "/config/device_registry":
            return [
                {
                    "id": "device-2",
                    "name": "Sensor",
                    "manufacturer": "Acme",
                    "model": "Model X",
                    "area_id": "area-1",
                }
            ]
        if path == "/config/entity_registry":
            return []
        raise AssertionError("Unexpected path")

    monkeypatch.setattr(exports, "_ha_get_json", fake_get)

    asyncio.run(exports.run_export("devices"))

    csv_path = config_dir / "system/devices.csv"
    rows = read_csv_rows(csv_path)
    assert rows[0] == [
        "device_id",
        "name",
        "manufacturer",
        "model",
        "area_id",
        "area_name",
    ]
    assert rows[1][0] == "device-2"
    assert rows[1][5] == "Office"


def test_export_missing_token_returns_error(tmp_path: Path, monkeypatch) -> None:
    load_main(tmp_path)
    exports = get_exports_module()
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)

    with pytest.raises(exports.ExportError) as exc:
        asyncio.run(exports.run_export("areas"))

    assert exc.value.status_code == 400
