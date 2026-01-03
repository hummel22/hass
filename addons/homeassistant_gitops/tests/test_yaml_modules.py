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


def write_yaml(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def get_yaml_modules_module():
    return sys.modules["gitops_bridge.yaml_modules"]


def test_list_yaml_modules_index_includes_packages_one_offs_and_unassigned(tmp_path: Path) -> None:
    _, config_dir = load_main(tmp_path)

    write_yaml(
        config_dir / "packages/kitchen/automations.yaml",
        [{"alias": "Kitchen automation", "trigger": []}],
    )
    write_yaml(config_dir / "packages/bedroom.yaml", {"sensor": {"bedroom_temp": {}}})
    write_yaml(
        config_dir / "automations/oneoff.yaml",
        [{"alias": "One-off", "trigger": []}],
    )
    write_yaml(config_dir / "scripts/turn_on.yaml", {"alias": "Turn on"})
    write_yaml(
        config_dir / "automations/automations.unassigned.yaml",
        [{"alias": "Unassigned", "trigger": []}],
    )

    yaml_modules = get_yaml_modules_module()
    index = yaml_modules.list_yaml_modules_index()
    modules = {module["id"]: module for module in index["modules"]}

    assert "package:kitchen" in modules
    assert "package:bedroom" in modules
    assert "one_offs:automations" in modules
    assert "one_offs:scripts" in modules
    assert "unassigned:automations" in modules
    assert "packages/kitchen/automations.yaml" in modules["package:kitchen"]["files"]
    assert "packages/bedroom.yaml" in modules["package:bedroom"]["files"]
    assert "automations/oneoff.yaml" in modules["one_offs:automations"]["files"]
    assert "scripts/turn_on.yaml" in modules["one_offs:scripts"]["files"]
    assert (
        "automations/automations.unassigned.yaml"
        in modules["unassigned:automations"]["files"]
    )


def test_module_file_round_trip(tmp_path: Path) -> None:
    _, config_dir = load_main(tmp_path)
    target = config_dir / "automations/demo.yaml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("alias: demo\n", encoding="utf-8")

    yaml_modules = get_yaml_modules_module()
    payload = yaml_modules.read_module_file("automations/demo.yaml")
    assert "alias: demo" in payload["content"]

    yaml_modules.write_module_file("automations/demo.yaml", "alias: updated\n")
    assert target.read_text(encoding="utf-8") == "alias: updated\n"

    yaml_modules.delete_module_file("automations/demo.yaml")
    assert not target.exists()


def test_module_file_rejects_invalid_path(tmp_path: Path) -> None:
    load_main(tmp_path)
    yaml_modules = get_yaml_modules_module()

    with pytest.raises(ValueError):
        yaml_modules.read_module_file("../secrets.yaml")


def test_sync_builds_domain_and_unassigned(tmp_path: Path) -> None:
    main, config_dir = load_main(tmp_path)

    write_yaml(
        config_dir / "packages/wakeup/automation.yaml",
        [{"alias": "Wake up", "trigger": []}],
    )
    write_yaml(
        config_dir / "automations/dishwasher.yaml",
        [{"alias": "Dishwasher", "trigger": []}],
    )
    write_yaml(
        config_dir / "automations.yaml",
        [{"alias": "UI only", "trigger": []}],
    )

    result = main.sync_yaml_modules()
    assert result["status"] == "synced"

    domain_items = yaml.safe_load((config_dir / "automations.yaml").read_text(encoding="utf-8"))
    assert len(domain_items) == 3
    assert all("id" in item for item in domain_items)
    aliases = {item.get("alias") for item in domain_items}
    assert {"Wake up", "Dishwasher", "UI only"} <= aliases

    unassigned = yaml.safe_load(
        (config_dir / "automations/automations.unassigned.yaml").read_text(encoding="utf-8")
    )
    assert unassigned[0]["alias"] == "UI only"

    mapping = yaml.safe_load(
        (config_dir / ".gitops/mappings/automation.yaml").read_text(encoding="utf-8")
    )
    assert len(mapping["entries"]) == 3


def test_sync_updates_from_domain_changes(tmp_path: Path) -> None:
    main, config_dir = load_main(tmp_path)

    write_yaml(
        config_dir / "packages/wakeup/automation.yaml",
        [{"alias": "Wake up", "trigger": []}],
    )
    write_yaml(
        config_dir / "automations.yaml",
        [{"alias": "UI only", "trigger": []}],
    )

    main.sync_yaml_modules()

    domain_items = yaml.safe_load((config_dir / "automations.yaml").read_text(encoding="utf-8"))
    for item in domain_items:
        if item.get("alias") == "Wake up":
            item["alias"] = "Wake up updated"
        if item.get("alias") == "UI only":
            item["alias"] = "UI updated"
    write_yaml(config_dir / "automations.yaml", domain_items)

    main.sync_yaml_modules()

    module_items = yaml.safe_load(
        (config_dir / "packages/wakeup/automation.yaml").read_text(encoding="utf-8")
    )
    assert module_items[0]["alias"] == "Wake up updated"

    unassigned_items = yaml.safe_load(
        (config_dir / "automations/automations.unassigned.yaml").read_text(encoding="utf-8")
    )
    assert unassigned_items[0]["alias"] == "UI updated"


def test_sync_prefers_modules_for_assigned_when_both_change(tmp_path: Path) -> None:
    main, config_dir = load_main(tmp_path)

    write_yaml(
        config_dir / "packages/wakeup/automation.yaml",
        [{"alias": "Wake up", "trigger": []}],
    )
    write_yaml(
        config_dir / "automations.yaml",
        [{"alias": "UI only", "trigger": []}],
    )

    main.sync_yaml_modules()

    module_path = config_dir / "packages/wakeup/automation.yaml"
    module_items = yaml.safe_load(module_path.read_text(encoding="utf-8"))
    module_items[0]["alias"] = "Module wins"
    write_yaml(module_path, module_items)

    domain_path = config_dir / "automations.yaml"
    domain_items = yaml.safe_load(domain_path.read_text(encoding="utf-8"))
    for item in domain_items:
        if item.get("alias") == "Wake up":
            item["alias"] = "Domain loses"
        if item.get("alias") == "UI only":
            item["alias"] = "UI wins"
    write_yaml(domain_path, domain_items)

    main.sync_yaml_modules()

    module_items = yaml.safe_load(module_path.read_text(encoding="utf-8"))
    assert module_items[0]["alias"] == "Module wins"

    unassigned_items = yaml.safe_load(
        (config_dir / "automations/automations.unassigned.yaml").read_text(encoding="utf-8")
    )
    assert unassigned_items[0]["alias"] == "UI wins"


def test_sync_helpers_split_to_domain_files(tmp_path: Path) -> None:
    main, config_dir = load_main(tmp_path)

    write_yaml(
        config_dir / "packages/wakeup/helpers.yaml",
        {
            "input_boolean": {"kitchen_motion": {"name": "Kitchen motion"}},
            "input_datetime": {"wake_time": {"name": "Wake time"}},
        },
    )

    main.sync_yaml_modules()

    input_boolean = yaml.safe_load(
        (config_dir / "input_boolean.yaml").read_text(encoding="utf-8")
    )
    input_datetime = yaml.safe_load(
        (config_dir / "input_datetime.yaml").read_text(encoding="utf-8")
    )
    assert "kitchen_motion" in input_boolean
    assert "wake_time" in input_datetime


def test_preview_yaml_modules_separates_build_and_update(tmp_path: Path) -> None:
    _, config_dir = load_main(tmp_path)

    write_yaml(
        config_dir / "packages/wakeup/automation.yaml",
        [{"alias": "Wake up", "trigger": [], "action": []}],
    )
    write_yaml(
        config_dir / "automations.yaml",
        [{"alias": "UI only", "trigger": [], "action": []}],
    )

    yaml_modules = get_yaml_modules_module()
    preview = yaml_modules.preview_yaml_modules()

    build_paths = {entry["path"] for entry in preview["build_diffs"]}
    update_paths = {entry["path"] for entry in preview["update_diffs"]}

    assert "automations.yaml" in build_paths
    assert "automations/automations.unassigned.yaml" in update_paths
    assert all(not path.startswith(".gitops/") for path in build_paths | update_paths)
    assert all(not path.startswith("system/") for path in build_paths | update_paths)
