from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Iterator, List, Optional

from .models import (
    HistoryPoint,
    InputHelper,
    InputHelperCreate,
    InputHelperRecord,
    InputHelperUpdate,
    InputValue,
    MQTTConfig,
)


def _serialize_value(value: Optional[InputValue]) -> Optional[str]:
    if value is None:
        return None
    return json.dumps(value)


def _deserialize_value(value: Optional[str]) -> Optional[InputValue]:
    if value is None:
        return None
    return json.loads(value)


def _serialize_options(options: Optional[List[str]]) -> Optional[str]:
    if not options:
        return None
    return json.dumps(options)


def _deserialize_options(value: Optional[str]) -> Optional[List[str]]:
    if value is None:
        return None
    loaded = json.loads(value)
    if not isinstance(loaded, list):
        return None
    return [str(item) for item in loaded]


def _serialize_identifiers(identifiers: Optional[List[str]]) -> Optional[str]:
    if not identifiers:
        return None
    return json.dumps(identifiers)


def _deserialize_identifiers(value: Optional[str]) -> List[str]:
    if value is None:
        return []
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(loaded, list):
        return []
    cleaned = []
    for item in loaded:
        text = str(item).strip()
        if text:
            cleaned.append(text)
    return cleaned


class InputHelperStore:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._init_db()
        self._migrate_from_json()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS helpers (
                    slug TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    helper_type TEXT NOT NULL,
                    description TEXT,
                    default_value TEXT,
                    options TEXT,
                    last_value TEXT,
                    last_measured_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    device_class TEXT,
                    unit_of_measurement TEXT,
                    component TEXT NOT NULL DEFAULT 'sensor',
                    unique_id TEXT NOT NULL,
                    object_id TEXT NOT NULL,
                    node_id TEXT,
                    state_topic TEXT NOT NULL,
                    availability_topic TEXT NOT NULL,
                    icon TEXT,
                    state_class TEXT,
                    force_update INTEGER NOT NULL DEFAULT 1,
                    device_name TEXT NOT NULL,
                    device_manufacturer TEXT,
                    device_model TEXT,
                    device_sw_version TEXT,
                    device_identifiers TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    helper_slug TEXT NOT NULL,
                    value TEXT NOT NULL,
                    measured_at TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(helper_slug) REFERENCES helpers(slug) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS mqtt_config (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    host TEXT NOT NULL,
                    port INTEGER NOT NULL,
                    username TEXT,
                    password TEXT,
                    client_id TEXT,
                    topic_prefix TEXT NOT NULL,
                    use_tls INTEGER NOT NULL DEFAULT 0
                )
                """
            )

            self._ensure_column(conn, "helpers", "last_measured_at", "TEXT")
            self._ensure_column(conn, "helpers", "component", "TEXT NOT NULL DEFAULT 'sensor'")
            self._ensure_column(conn, "helpers", "unique_id", "TEXT")
            self._ensure_column(conn, "helpers", "object_id", "TEXT")
            self._ensure_column(conn, "helpers", "node_id", "TEXT")
            self._ensure_column(conn, "helpers", "state_topic", "TEXT")
            self._ensure_column(conn, "helpers", "availability_topic", "TEXT")
            self._ensure_column(conn, "helpers", "icon", "TEXT")
            self._ensure_column(conn, "helpers", "state_class", "TEXT")
            self._ensure_column(conn, "helpers", "force_update", "INTEGER NOT NULL DEFAULT 1")
            self._ensure_column(conn, "helpers", "device_name", "TEXT")
            self._ensure_column(conn, "helpers", "device_manufacturer", "TEXT")
            self._ensure_column(conn, "helpers", "device_model", "TEXT")
            self._ensure_column(conn, "helpers", "device_sw_version", "TEXT")
            self._ensure_column(conn, "helpers", "device_identifiers", "TEXT")
            self._ensure_column(conn, "history", "measured_at", "TEXT")

    @staticmethod
    def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        existing = {info["name"] for info in conn.execute(f"PRAGMA table_info({table})")}
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def _migrate_from_json(self) -> None:
        legacy_path = self._db_path.with_suffix(".json")
        if not legacy_path.exists():
            return

        try:
            with legacy_path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return

        inputs = data.get("inputs", [])
        if not inputs:
            return

        with self._connection() as conn:
            existing = conn.execute("SELECT COUNT(*) AS count FROM helpers").fetchone()
            if existing and existing["count"]:
                return

            for item in inputs:
                try:
                    helper = InputHelper(**item)
                except Exception:  # noqa: BLE001
                    continue
                conn.execute(
                    """
                    INSERT OR REPLACE INTO helpers (
                        slug, name, entity_id, helper_type, description, default_value,
                        options, last_value, last_measured_at, created_at, updated_at,
                        device_class, unit_of_measurement, component, unique_id, object_id,
                        node_id, state_topic, availability_topic, icon, state_class,
                        force_update, device_name, device_manufacturer, device_model,
                        device_sw_version, device_identifiers
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    helper.slug,
                    helper.name,
                    helper.entity_id,
                    helper.type.value,
                    helper.description,
                    _serialize_value(helper.default_value),
                    _serialize_options(helper.options),
                    _serialize_value(helper.last_value),
                    helper.last_measured_at.isoformat() if helper.last_measured_at else None,
                    helper.created_at.isoformat(),
                    helper.updated_at.isoformat(),
                    helper.device_class,
                    helper.unit_of_measurement,
                    helper.component,
                    helper.unique_id,
                    helper.object_id,
                    helper.node_id,
                    helper.state_topic,
                    helper.availability_topic,
                    helper.icon,
                    helper.state_class,
                    int(helper.force_update),
                    helper.device_name,
                    helper.device_manufacturer,
                    helper.device_model,
                    helper.device_sw_version,
                    _serialize_identifiers(helper.device_identifiers),
                ),
            )

    def _row_to_helper(self, row: sqlite3.Row) -> InputHelper:
        keys = set(row.keys())
        return InputHelper(
            slug=row["slug"],
            name=row["name"],
            entity_id=row["entity_id"],
            type=row["helper_type"],
            description=row["description"],
            default_value=_deserialize_value(row["default_value"]),
            options=_deserialize_options(row["options"]),
            last_value=_deserialize_value(row["last_value"]),
            last_measured_at=datetime.fromisoformat(row["last_measured_at"])
            if "last_measured_at" in keys and row["last_measured_at"]
            else None,
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            device_class=row["device_class"],
            unit_of_measurement=row["unit_of_measurement"],
            component=row.get("component", "sensor"),
            unique_id=row.get("unique_id", row["slug"]),
            object_id=row.get("object_id", row["slug"]),
            node_id=row.get("node_id"),
            state_topic=row.get("state_topic", f"{row['slug']}/state"),
            availability_topic=row.get(
                "availability_topic", f"{row['slug']}/availability"
            ),
            icon=row.get("icon"),
            state_class=row.get("state_class"),
            force_update=bool(row.get("force_update", 1)),
            device_name=row.get("device_name", row["name"]),
            device_manufacturer=row.get("device_manufacturer"),
            device_model=row.get("device_model"),
            device_sw_version=row.get("device_sw_version"),
            device_identifiers=_deserialize_identifiers(row.get("device_identifiers")),
        )

    def list_helpers(self) -> List[InputHelper]:
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM helpers ORDER BY name COLLATE NOCASE"
            ).fetchall()
        return [self._row_to_helper(row) for row in rows]

    def get_helper(self, slug: str) -> Optional[InputHelperRecord]:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM helpers WHERE slug = ?",
                (slug,),
            ).fetchone()
        if row is None:
            return None
        return InputHelperRecord(self._row_to_helper(row))

    def create_helper(self, payload: InputHelperCreate) -> InputHelper:
        record = InputHelperRecord.create(payload)
        helper = record.helper

        with self._lock:
            if self.get_helper(helper.slug) is not None:
                raise ValueError(f"Helper with slug '{helper.slug}' already exists.")
            with self._connection() as conn:
                conn.execute(
                    """
                    INSERT INTO helpers (
                        slug, name, entity_id, helper_type, description, default_value,
                        options, last_value, last_measured_at, created_at, updated_at,
                        device_class, unit_of_measurement, component, unique_id, object_id,
                        node_id, state_topic, availability_topic, icon, state_class,
                        force_update, device_name, device_manufacturer, device_model,
                        device_sw_version, device_identifiers
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        helper.slug,
                        helper.name,
                        helper.entity_id,
                        helper.type.value,
                        helper.description,
                        _serialize_value(helper.default_value),
                        _serialize_options(helper.options),
                        _serialize_value(helper.last_value),
                        helper.last_measured_at.isoformat() if helper.last_measured_at else None,
                        helper.created_at.isoformat(),
                        helper.updated_at.isoformat(),
                        helper.device_class,
                        helper.unit_of_measurement,
                        helper.component,
                        helper.unique_id,
                        helper.object_id,
                        helper.node_id,
                        helper.state_topic,
                        helper.availability_topic,
                        helper.icon,
                        helper.state_class,
                        int(helper.force_update),
                        helper.device_name,
                        helper.device_manufacturer,
                        helper.device_model,
                        helper.device_sw_version,
                        _serialize_identifiers(helper.device_identifiers),
                    ),
                )
        return helper

    def update_helper(self, slug: str, payload: InputHelperUpdate) -> InputHelper:
        with self._lock:
            existing = self.get_helper(slug)
            if existing is None:
                raise KeyError(f"Helper '{slug}' not found.")
            existing.update(payload)
            helper = existing.helper
            with self._connection() as conn:
                conn.execute(
                    """
                    UPDATE helpers
                       SET name = ?,
                           entity_id = ?,
                           description = ?,
                           default_value = ?,
                           options = ?,
                           last_value = ?,
                           last_measured_at = ?,
                           updated_at = ?,
                           device_class = ?,
                           unit_of_measurement = ?,
                           component = ?,
                           unique_id = ?,
                           object_id = ?,
                           node_id = ?,
                           state_topic = ?,
                           availability_topic = ?,
                           icon = ?,
                           state_class = ?,
                           force_update = ?,
                           device_name = ?,
                           device_manufacturer = ?,
                           device_model = ?,
                           device_sw_version = ?,
                           device_identifiers = ?
                     WHERE slug = ?
                    """,
                    (
                        helper.name,
                        helper.entity_id,
                        helper.description,
                        _serialize_value(helper.default_value),
                        _serialize_options(helper.options),
                        _serialize_value(helper.last_value),
                        helper.last_measured_at.isoformat() if helper.last_measured_at else None,
                        helper.updated_at.isoformat(),
                        helper.device_class,
                        helper.unit_of_measurement,
                        helper.component,
                        helper.unique_id,
                        helper.object_id,
                        helper.node_id,
                        helper.state_topic,
                        helper.availability_topic,
                        helper.icon,
                        helper.state_class,
                        int(helper.force_update),
                        helper.device_name,
                        helper.device_manufacturer,
                        helper.device_model,
                        helper.device_sw_version,
                        _serialize_identifiers(helper.device_identifiers),
                        helper.slug,
                    ),
                )
        return helper

    def delete_helper(self, slug: str) -> None:
        with self._lock:
            with self._connection() as conn:
                cursor = conn.execute(
                    "DELETE FROM helpers WHERE slug = ?",
                    (slug,),
                )
                if cursor.rowcount == 0:
                    raise KeyError(f"Helper '{slug}' not found.")

    def set_last_value(self, slug: str, value: InputValue, *, measured_at: datetime) -> InputHelper:
        timestamp = datetime.now(timezone.utc).isoformat()
        measured_iso = measured_at.astimezone(timezone.utc).isoformat()
        serialized_value = _serialize_value(value)
        with self._lock:
            with self._connection() as conn:
                cursor = conn.execute(
                    """
                    UPDATE helpers
                       SET last_value = ?,
                           last_measured_at = ?,
                           updated_at = ?
                     WHERE slug = ?
                    """,
                    (serialized_value, measured_iso, timestamp, slug),
                )
                if cursor.rowcount == 0:
                    raise KeyError(f"Helper '{slug}' not found.")
                conn.execute(
                    """
                    INSERT INTO history (helper_slug, value, measured_at, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (slug, serialized_value, measured_iso, timestamp),
                )
                row = conn.execute(
                    "SELECT * FROM helpers WHERE slug = ?",
                    (slug,),
                ).fetchone()
        if row is None:
            raise KeyError(f"Helper '{slug}' not found.")
        return self._row_to_helper(row)

    def list_history(self, slug: str, limit: int = 200) -> List[HistoryPoint]:
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT value, measured_at, created_at
                  FROM history
                 WHERE helper_slug = ?
              ORDER BY datetime(created_at) ASC
                 LIMIT ?
                """,
                (slug, limit),
            ).fetchall()
        history: List[HistoryPoint] = []
        for row in rows:
            recorded_at = datetime.fromisoformat(row["created_at"])
            value = _deserialize_value(row["value"])
            if value is None:
                continue
            measured_source = row["measured_at"] or row["created_at"]
            measured_at = datetime.fromisoformat(measured_source)
            history.append(
                HistoryPoint(
                    measured_at=measured_at,
                    recorded_at=recorded_at,
                    value=value,
                )
            )
        return history

    def get_mqtt_config(self) -> Optional[MQTTConfig]:
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM mqtt_config WHERE id = 1").fetchone()
        if row is None:
            return None
        discovery_prefix = (row["topic_prefix"] or "homeassistant").strip("/") or "homeassistant"
        return MQTTConfig(
            host=row["host"],
            port=row["port"],
            username=row["username"],
            password=row["password"],
            client_id=row["client_id"],
            discovery_prefix=discovery_prefix,
            use_tls=bool(row["use_tls"]),
        )

    def save_mqtt_config(self, config: MQTTConfig) -> MQTTConfig:
        discovery_prefix = (config.discovery_prefix or "homeassistant").strip("/") or "homeassistant"
        stored = config.model_copy(update={"discovery_prefix": discovery_prefix})
        with self._lock:
            with self._connection() as conn:
                conn.execute(
                    """
                    INSERT INTO mqtt_config (
                        id, host, port, username, password, client_id, topic_prefix, use_tls
                    ) VALUES (1, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        host = excluded.host,
                        port = excluded.port,
                        username = excluded.username,
                        password = excluded.password,
                        client_id = excluded.client_id,
                        topic_prefix = excluded.topic_prefix,
                        use_tls = excluded.use_tls
                    """,
                    (
                        stored.host,
                        stored.port,
                        stored.username,
                        stored.password,
                        stored.client_id,
                        stored.discovery_prefix,
                        int(stored.use_tls),
                    ),
                )
        return stored


__all__ = ["InputHelperStore"]
