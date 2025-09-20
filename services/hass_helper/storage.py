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
            json.dump(
                data,
                handle,
                sort_keys=True,
                separators=(",", ":"),
            )

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
            data_dir / "integrations.json", {"selected_domains": []}
        )
        self.entities_store = JSONStorage(
            data_dir / "entities.json", {"devices": []}
        )
        self.blacklist_store = JSONStorage(
            data_dir / "blacklist.json", {"entities": [], "devices": []}
        )
        self.whitelist_store = JSONStorage(
            data_dir / "whitelist.json", {"entities": []}
        )

    # Integrations --------------------------------------------------------
    def _extract_domain_entries(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        raw_entries = data.get("selected_domains")
        if raw_entries is None:
            raw_entries = data.get("selected", [])

        entries: List[Dict[str, Any]] = []
        for item in raw_entries or []:
            domain: str | None
            title: str | None = None
            if isinstance(item, str):
                domain = item
            elif isinstance(item, dict):
                domain = item.get("domain")
                title = item.get("title")
            else:
                continue
            if not domain:
                continue
            if not any(entry["domain"] == domain for entry in entries):
                entry: Dict[str, Any] = {"domain": domain}
                if title:
                    entry["title"] = title
                entries.append(entry)
        entries.sort(key=lambda entry: entry.get("domain", ""))
        return entries

    def get_selected_domains(self) -> List[Dict[str, Any]]:
        data = self.integrations_store.read()
        entries = self._extract_domain_entries(data)
        cleaned_entries = [self._remove_nulls(entry) for entry in entries]
        if data.get("selected_domains") != cleaned_entries:
            self.integrations_store.write({"selected_domains": cleaned_entries})
        return cleaned_entries

    def add_domain(self, domain: str, *, title: str | None = None) -> List[Dict[str, Any]]:
        def updater(data: Dict[str, Any]) -> Dict[str, Any]:
            entries = self._extract_domain_entries(data)
            if not any(entry["domain"] == domain for entry in entries):
                entry: Dict[str, Any] = {"domain": domain}
                if title:
                    entry["title"] = title
                entries.append(entry)
                entries.sort(key=lambda entry: entry.get("domain", ""))
            data.clear()
            data["selected_domains"] = [
                DataRepository._remove_nulls(entry) for entry in entries
            ]
            return data

        updated = self.integrations_store.update(updater)
        return list(updated.get("selected_domains", []))

    def remove_domain(self, domain: str) -> List[Dict[str, Any]]:
        def updater(data: Dict[str, Any]) -> Dict[str, Any]:
            entries = self._extract_domain_entries(data)
            filtered = [entry for entry in entries if entry["domain"] != domain]
            data.clear()
            data["selected_domains"] = [
                DataRepository._remove_nulls(entry) for entry in filtered
            ]
            return data

        updated = self.integrations_store.update(updater)
        return list(updated.get("selected_domains", []))

    # Entities ------------------------------------------------------------
    @staticmethod
    def _remove_nulls(value: Any) -> Any:
        if isinstance(value, dict):
            cleaned: Dict[str, Any] = {}
            for key, item in value.items():
                if item is None:
                    continue
                cleaned[key] = DataRepository._remove_nulls(item)
            return cleaned
        if isinstance(value, list):
            cleaned_list = []
            for item in value:
                if item is None:
                    continue
                cleaned_list.append(DataRepository._remove_nulls(item))
            return cleaned_list
        return value

    @staticmethod
    def _sanitize_identifiers(values: Any) -> List[Any]:
        if isinstance(values, list):
            iterable = values
        elif isinstance(values, (set, tuple)):
            iterable = list(values)
        else:
            iterable = [values] if values is not None else []
        cleaned: List[Any] = []
        for item in iterable:
            if item is None:
                continue
            if isinstance(item, (set, tuple)):
                cleaned.append([sub for sub in item if sub is not None])
            else:
                cleaned.append(item)
        return cleaned

    def _sanitize_entity(
        self,
        entity: Dict[str, Any],
        *,
        device_id: str | None,
        device_area: str | None,
    ) -> Dict[str, Any]:
        entity_id = entity.get("entity_id")
        if not entity_id:
            return {}

        attributes = entity.get("attributes")
        if isinstance(attributes, dict):
            attributes = dict(attributes)
        else:
            attributes = {}

        sanitized: Dict[str, Any] = {"entity_id": entity_id}

        integration_id = (
            entity.get("integration_id")
            or entity.get("integration")
            or attributes.get("integration_id")
        )
        if integration_id:
            sanitized["integration_id"] = integration_id

        if device_id:
            sanitized["device"] = device_id

        area_value = (
            entity.get("area")
            or entity.get("area_id")
            or attributes.get("area")
            or device_area
        )
        if area_value:
            sanitized["area"] = area_value

        friendly_name = entity.get("friendly_name") or attributes.get(
            "friendly_name"
        )
        if friendly_name:
            sanitized["friendly_name"] = friendly_name

        object_id = entity.get("object_id") or attributes.get("object_id")
        if object_id:
            sanitized["object_id"] = object_id

        last_changed = entity.get("last_changed") or attributes.get("last_changed")
        if last_changed:
            sanitized["last_changed"] = last_changed

        name_candidates = [
            entity.get("name"),
            friendly_name,
            object_id,
            entity_id,
        ]
        for candidate in name_candidates:
            if candidate:
                sanitized["name"] = candidate
                break

        for key in (
            "device_class",
            "state_class",
            "icon",
            "entity_category",
        ):
            value = entity.get(key)
            if value is None:
                value = attributes.get(key)
            if value is not None:
                sanitized[key] = value

        unit_value = (
            entity.get("unit_of_measurement")
            or entity.get("unit")
            or attributes.get("unit_of_measurement")
            or attributes.get("unit")
            or attributes.get("native_unit_of_measurement")
        )
        if unit_value is not None:
            sanitized["unit_of_measurement"] = unit_value

        native_unit = attributes.get("native_unit_of_measurement")
        if native_unit is not None:
            sanitized.setdefault("native_unit_of_measurement", native_unit)

        disabled_by = entity.get("disabled_by")
        if disabled_by:
            sanitized["disabled_by"] = disabled_by

        # Flatten any remaining attribute fields that have not already been copied.
        for key, value in attributes.items():
            if value is None:
                continue
            if key in {"friendly_name", "object_id", "area", "last_changed"}:
                sanitized.setdefault(key, value)
            elif key == "unit":
                sanitized.setdefault("unit_of_measurement", value)
            else:
                sanitized.setdefault(key, value)

        # Copy selected passthrough fields, skipping those slated for removal.
        for key, value in entity.items():
            if key in {
                "device_id",
                "state",
                "original_name",
                "unique_id",
                "area_id",
                "attributes",
            }:
                continue
            if key in {"unit", "integration"}:
                continue
            if value is None:
                continue
            sanitized.setdefault(key, value)

        return self._remove_nulls(sanitized)

    def _sanitize_devices(self, devices: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        sanitized_devices: List[Dict[str, Any]] = []
        for device in devices:
            if not isinstance(device, dict):
                continue
            device_id = device.get("id") or device.get("device_id")
            if not device_id:
                continue

            sanitized_device: Dict[str, Any] = {"id": device_id}

            for key in (
                "name",
                "name_by_user",
                "manufacturer",
                "model",
                "sw_version",
                "configuration_url",
                "area",
                "area_id",
                "via_device_id",
                "integration_id",
            ):
                value = device.get(key)
                if value is None and key == "area":
                    value = device.get("area_id")
                if value is None:
                    continue
                sanitized_device[key] = value

            identifiers = self._sanitize_identifiers(device.get("identifiers"))
            if identifiers:
                sanitized_device["identifiers"] = identifiers

            entities = device.get("entities")
            sanitized_entities: List[Dict[str, Any]] = []
            if isinstance(entities, list):
                for entity in entities:
                    if not isinstance(entity, dict):
                        continue
                    sanitized_entity = self._sanitize_entity(
                        entity,
                        device_id=device_id,
                        device_area=sanitized_device.get("area")
                        or sanitized_device.get("area_id"),
                    )
                    if sanitized_entity:
                        sanitized_entities.append(sanitized_entity)
            sanitized_entities.sort(key=lambda item: str(item.get("entity_id") or "").lower())
            sanitized_device["entities"] = sanitized_entities

            sanitized_devices.append(self._remove_nulls(sanitized_device))

        sanitized_devices.sort(key=lambda item: str(item.get("id") or "").lower())
        return sanitized_devices

    def save_entities(self, devices: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        sanitized = self._sanitize_devices(devices)
        self.entities_store.write({"devices": sanitized})
        return sanitized

    def get_entities(self) -> Dict[str, Any]:
        data = self.entities_store.read()
        if not isinstance(data, dict):
            return {"devices": []}
        devices = data.get("devices")
        if isinstance(devices, list):
            sanitized_devices = self._sanitize_devices(devices)
            sanitized_payload = {"devices": sanitized_devices}
            if sanitized_payload != data:
                self.entities_store.write(sanitized_payload)
            return sanitized_payload

        # Backwards compatibility: migrate old entity/device split format.
        legacy_entities = data.get("entities")
        legacy_devices = data.get("devices")

        device_map: Dict[str, Dict[str, Any]] = {}

        if isinstance(legacy_devices, list):
            for item in legacy_devices:
                if not isinstance(item, dict):
                    continue
                device_id = item.get("id")
                if not device_id:
                    continue
                record = json.loads(json.dumps(item))
                record["entities"] = []
                device_map[device_id] = record

        if isinstance(legacy_entities, list):
            for entity in legacy_entities:
                if not isinstance(entity, dict):
                    continue
                device_id = entity.get("device_id")
                if not device_id:
                    continue
                record = device_map.setdefault(
                    device_id,
                    {"id": device_id, "entities": []},
                )
                if not isinstance(record.get("entities"), list):
                    record["entities"] = []
                record["entities"].append(json.loads(json.dumps(entity)))

        migrated = {"devices": list(device_map.values())}
        self.entities_store.write(migrated)
        return migrated

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
        self._purge_entities_store(target_type, target_id)
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

    def _purge_entities_store(self, target_type: str, target_id: str) -> None:
        """Remove blacklisted entries from the persisted entity snapshot."""

        target_type = target_type.lower()
        if target_type not in {"entity", "device"}:
            return

        def updater(data: Dict[str, Any]) -> Dict[str, Any]:
            if not isinstance(data, dict):
                return {"devices": []}

            devices = data.get("devices")
            if not isinstance(devices, list):
                data["devices"] = []
                return data

            changed = False
            new_devices: List[Dict[str, Any]] = []

            for device in devices:
                if not isinstance(device, dict):
                    continue

                device_id = device.get("id") or device.get("device_id")
                if target_type == "device" and device_id == target_id:
                    changed = True
                    continue

                sanitized_device: Dict[str, Any] = json.loads(json.dumps(device))
                entities = sanitized_device.get("entities")
                if not isinstance(entities, list):
                    entities = []

                sanitized_entities: List[Dict[str, Any]] = []
                removed_entity = False

                for entity in entities:
                    if not isinstance(entity, dict):
                        continue

                    entity_id = entity.get("entity_id")
                    if target_type == "entity" and entity_id == target_id:
                        removed_entity = True
                        changed = True
                        continue

                    sanitized_entities.append(entity)

                sanitized_device["entities"] = sanitized_entities

                if target_type == "entity" and removed_entity and not sanitized_entities:
                    # Drop devices that no longer contain entities after the purge.
                    continue

                new_devices.append(sanitized_device)

            if not changed:
                return data

            data = json.loads(json.dumps(data))
            data["devices"] = new_devices
            return data

        self.entities_store.update(updater)

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
