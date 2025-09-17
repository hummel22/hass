"""Persistent storage helpers for the hass_helper service."""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List


class JSONStorage:
    """Thread-safe JSON file storage wrapper."""

    def __init__(self, path: Path, default: Any) -> None:
        self.path = path
        self.default = default
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Ensure the file exists with default contents.
        with self._lock:
            if not self.path.exists():
                self._write_locked(self._copy_default())

    def _copy_default(self) -> Any:
        """Return a deep copy of the default value."""
        return json.loads(json.dumps(self.default))

    def _read_locked(self) -> Any:
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        except FileNotFoundError:
            data = self._copy_default()
            self._write_locked(data)
            return data
        except json.JSONDecodeError:
            data = self._copy_default()
            self._write_locked(data)
            return data

    def _write_locked(self, data: Any) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, sort_keys=True)

    def read(self) -> Any:
        with self._lock:
            return self._read_locked()

    def write(self, data: Any) -> None:
        with self._lock:
            self._write_locked(data)

    def update(self, updater: Callable[[Any], Any]) -> Any:
        with self._lock:
            data = self._read_locked()
            new_data = updater(data)
            self._write_locked(new_data)
            return new_data


class DataRepository:
    """High level wrapper around the JSON storage files."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.integrations_store = JSONStorage(
            data_dir / "integrations.json", {"selected": []}
        )
        self.entities_store = JSONStorage(
            data_dir / "entities.json", {"entities": [], "devices": []}
        )
        self.blacklist_store = JSONStorage(
            data_dir / "blacklist.json", {"entities": [], "devices": []}
        )
        self.whitelist_store = JSONStorage(
            data_dir / "whitelist.json", {"entities": []}
        )

    # Integrations --------------------------------------------------------
    def get_selected_integrations(self) -> List[Dict[str, Any]]:
        data = self.integrations_store.read()
        return list(data.get("selected", []))

    def add_integration(self, integration: Dict[str, Any]) -> List[Dict[str, Any]]:
        def updater(data: Dict[str, Any]) -> Dict[str, Any]:
            selected: List[Dict[str, Any]] = data.setdefault("selected", [])
            if not any(entry.get("entry_id") == integration.get("entry_id") for entry in selected):
                selected.append(
                    {
                        "entry_id": integration.get("entry_id"),
                        "domain": integration.get("domain"),
                        "title": integration.get("title"),
                    }
                )
            return data

        updated = self.integrations_store.update(updater)
        return list(updated.get("selected", []))

    def remove_integration(self, integration_id: str) -> List[Dict[str, Any]]:
        def updater(data: Dict[str, Any]) -> Dict[str, Any]:
            selected: List[Dict[str, Any]] = data.setdefault("selected", [])
            data["selected"] = [
                entry for entry in selected if entry.get("entry_id") != integration_id
            ]
            return data

        updated = self.integrations_store.update(updater)
        return list(updated.get("selected", []))

    # Entities ------------------------------------------------------------
    def save_entities(self, entities: List[Dict[str, Any]], devices: List[Dict[str, Any]]) -> None:
        self.entities_store.write({"entities": entities, "devices": devices})

    def get_entities(self) -> Dict[str, Any]:
        return self.entities_store.read()

    # Blacklist -----------------------------------------------------------
    def get_blacklist(self) -> Dict[str, List[str]]:
        data = self.blacklist_store.read()
        return {
            "entities": list(data.get("entities", [])),
            "devices": list(data.get("devices", [])),
        }

    def add_to_blacklist(self, target_type: str, target_id: str) -> Dict[str, List[str]]:
        target_type = target_type.lower()
        if target_type not in {"entity", "device"}:
            raise ValueError("target_type must be 'entity' or 'device'")

        def updater(data: Dict[str, List[str]]) -> Dict[str, List[str]]:
            key = "entities" if target_type == "entity" else "devices"
            entries: List[str] = data.setdefault(key, [])
            if target_id not in entries:
                entries.append(target_id)
            return data

        updated = self.blacklist_store.update(updater)
        return {
            "entities": list(updated.get("entities", [])),
            "devices": list(updated.get("devices", [])),
        }

    def remove_from_blacklist(self, target_type: str, target_id: str) -> Dict[str, List[str]]:
        target_type = target_type.lower()
        if target_type not in {"entity", "device"}:
            raise ValueError("target_type must be 'entity' or 'device'")

        def updater(data: Dict[str, List[str]]) -> Dict[str, List[str]]:
            key = "entities" if target_type == "entity" else "devices"
            entries: List[str] = data.setdefault(key, [])
            data[key] = [entry for entry in entries if entry != target_id]
            return data

        updated = self.blacklist_store.update(updater)
        return {
            "entities": list(updated.get("entities", [])),
            "devices": list(updated.get("devices", [])),
        }

    # Whitelist -----------------------------------------------------------
    def get_whitelist(self) -> Dict[str, List[str]]:
        data = self.whitelist_store.read()
        return {"entities": list(data.get("entities", []))}

    def add_to_whitelist(self, entity_id: str) -> Dict[str, List[str]]:
        def updater(data: Dict[str, List[str]]) -> Dict[str, List[str]]:
            entries: List[str] = data.setdefault("entities", [])
            if entity_id not in entries:
                entries.append(entity_id)
            return data

        updated = self.whitelist_store.update(updater)
        return {"entities": list(updated.get("entities", []))}

    def remove_from_whitelist(self, entity_id: str) -> Dict[str, List[str]]:
        def updater(data: Dict[str, List[str]]) -> Dict[str, List[str]]:
            entries: List[str] = data.setdefault("entities", [])
            data["entities"] = [entry for entry in entries if entry != entity_id]
            return data

        updated = self.whitelist_store.update(updater)
        return {"entities": list(updated.get("entities", []))}

    # Helpers -------------------------------------------------------------
    def is_entity_allowed(
        self,
        entity_id: str,
        device_id: str | None,
        *,
        blacklist: Dict[str, List[str]] | None = None,
        whitelist: Dict[str, List[str]] | None = None,
    ) -> bool:
        if whitelist is None:
            whitelist = self.get_whitelist()
        if blacklist is None:
            blacklist = self.get_blacklist()

        whitelist_entities = set(whitelist.get("entities", []))
        blacklist_entities = set(blacklist.get("entities", []))
        blacklist_devices = set(blacklist.get("devices", []))

        if entity_id in whitelist_entities:
            return True
        if entity_id in blacklist_entities:
            return False
        if device_id and device_id in blacklist_devices:
            return False
        return True


__all__ = ["DataRepository"]
