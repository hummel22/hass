from __future__ import annotations

import json
import secrets
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Callable, Dict, Iterator, List, Optional, Sequence, Tuple

from .models import (
    ApiUser,
    ApiUserCreate,
    ApiUserUpdate,
    EntityKind,
    EntityTransportType,
    HASSEMSStatisticsMode,
    HistoryCursorEvent,
    HistoryPoint,
    HistoryPointUpdate,
    ManagedEntity,
    ManagedEntityCreate,
    ManagedEntityRecord,
    ManagedEntityUpdate,
    InputValue,
    IntegrationConnectionCreate,
    IntegrationConnectionDetail,
    IntegrationConnectionHistoryItem,
    IntegrationConnectionOwner,
    IntegrationConnectionSummary,
    MQTTConfig,
    WebhookRegistration,
    WebhookSubscription,
    slugify_identifier,
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


def _serialize_metadata(metadata: Optional[Dict[str, Any]]) -> Optional[str]:
    if not metadata:
        return None
    return json.dumps(metadata)


def _deserialize_metadata(value: Optional[str]) -> Optional[Dict[str, Any]]:
    if not value:
        return None
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return None
    if not isinstance(loaded, dict):
        return None
    return loaded


@dataclass
class WebhookTarget:
    id: int
    user_id: int
    webhook_url: str
    secret: Optional[str]
    token: str
    description: Optional[str]
    metadata: Optional[Dict[str, Any]]
    created_at: datetime
    updated_at: datetime


HISTORICAL_THRESHOLD = timedelta(days=10)


def _generate_history_cursor() -> str:
    return secrets.token_hex(16)


def _is_historical_timestamp(measured_at: Optional[datetime]) -> bool:
    if measured_at is None:
        return False
    now = datetime.now(timezone.utc)
    target = measured_at.astimezone(timezone.utc)
    return (now - target) >= HISTORICAL_THRESHOLD


SchemaMigration = Callable[[sqlite3.Connection], None]


def _migration_add_history_is_historic(conn: sqlite3.Connection) -> None:
    existing = {info["name"] for info in conn.execute("PRAGMA table_info(history)")}
    if "is_historic" not in existing:
        conn.execute(
            "ALTER TABLE history ADD COLUMN is_historic INTEGER NOT NULL DEFAULT 0"
        )

    threshold = datetime.now(timezone.utc) - HISTORICAL_THRESHOLD
    rows = conn.execute(
        "SELECT id, measured_at, created_at FROM history"
    ).fetchall()
    for row in rows:
        measured_raw = row["measured_at"] or row["created_at"]
        try:
            measured_dt = datetime.fromisoformat(measured_raw)
        except (TypeError, ValueError):
            continue
        if measured_dt <= threshold:
            conn.execute(
                "UPDATE history SET is_historic = 1 WHERE id = ?",
                (row["id"],),
            )


SCHEMA_MIGRATIONS: Sequence[Tuple[int, SchemaMigration]] = (
    (1, _migration_add_history_is_historic),
)


class ManagedEntityStore:
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
                CREATE TABLE IF NOT EXISTS entities (
                    slug TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    entity_kind TEXT NOT NULL,
                    entity_type TEXT NOT NULL DEFAULT 'mqtt',
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
                    device_id TEXT,
                    device_manufacturer TEXT,
                    device_model TEXT,
                    device_sw_version TEXT,
                    device_identifiers TEXT,
                    statistics_mode TEXT DEFAULT 'linear',
                    ha_enabled INTEGER NOT NULL DEFAULT 1,
                    history_cursor TEXT,
                    history_changed_at TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_slug TEXT NOT NULL,
                    value TEXT NOT NULL,
                    measured_at TEXT,
                    history_cursor TEXT,
                    is_historic INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(entity_slug) REFERENCES entities(slug) ON DELETE CASCADE
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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS api_users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    token TEXT NOT NULL UNIQUE,
                    is_superuser INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS webhook_subscriptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    description TEXT,
                    webhook_url TEXT NOT NULL,
                    secret TEXT,
                    metadata TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(user_id, description),
                    FOREIGN KEY(user_id) REFERENCES api_users(id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS integration_connections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    api_user_id INTEGER NOT NULL,
                    entry_id TEXT NOT NULL UNIQUE,
                    title TEXT,
                    entity_count INTEGER NOT NULL DEFAULT 0,
                    included_entities TEXT,
                    ignored_entities TEXT,
                    metadata TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_seen TEXT,
                    FOREIGN KEY(api_user_id) REFERENCES api_users(id) ON DELETE CASCADE
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS history_cursor_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_slug TEXT NOT NULL,
                    history_cursor TEXT NOT NULL,
                    changed_at TEXT NOT NULL,
                    UNIQUE(entity_slug, history_cursor),
                    FOREIGN KEY(entity_slug) REFERENCES entities(slug) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_history_cursor_events_entity
                    ON history_cursor_events (entity_slug, changed_at)
                """
            )

            self._ensure_column(conn, "entities", "last_measured_at", "TEXT")
            self._ensure_column(conn, "entities", "component", "TEXT NOT NULL DEFAULT 'sensor'")
            self._ensure_column(conn, "entities", "unique_id", "TEXT")
            self._ensure_column(conn, "entities", "object_id", "TEXT")
            self._ensure_column(conn, "entities", "node_id", "TEXT")
            self._ensure_column(conn, "entities", "state_topic", "TEXT")
            self._ensure_column(conn, "entities", "availability_topic", "TEXT")
            self._ensure_column(conn, "entities", "entity_type", "TEXT NOT NULL DEFAULT 'mqtt'")
            self._ensure_column(conn, "entities", "icon", "TEXT")
            self._ensure_column(conn, "entities", "state_class", "TEXT")
            self._ensure_column(conn, "entities", "force_update", "INTEGER NOT NULL DEFAULT 1")
            self._ensure_column(conn, "entities", "device_name", "TEXT")
            self._ensure_column(conn, "entities", "device_id", "TEXT")
            self._ensure_column(conn, "entities", "device_manufacturer", "TEXT")
            self._ensure_column(conn, "entities", "device_model", "TEXT")
            self._ensure_column(conn, "entities", "device_sw_version", "TEXT")
            self._ensure_column(conn, "entities", "device_identifiers", "TEXT")
            self._ensure_column(
                conn, "entities", "statistics_mode", "TEXT DEFAULT 'linear'"
            )
            self._ensure_column(
                conn, "entities", "ha_enabled", "INTEGER NOT NULL DEFAULT 1"
            )
            self._ensure_column(conn, "entities", "history_cursor", "TEXT")
            self._ensure_column(conn, "entities", "history_changed_at", "TEXT")
            self._ensure_column(conn, "history", "measured_at", "TEXT")
            self._ensure_column(conn, "history", "history_cursor", "TEXT")
            self._ensure_column(conn, "api_users", "is_superuser", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "webhook_subscriptions", "metadata", "TEXT")
            self._ensure_column(conn, "integration_connections", "last_seen", "TEXT")
            self._ensure_column(conn, "integration_connections", "entity_count", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "integration_connections", "metadata", "TEXT")

            self._apply_migrations(conn)
            self._backfill_history_cursor_events(conn)

    @staticmethod
    def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        existing = {info["name"] for info in conn.execute(f"PRAGMA table_info({table})")}
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def _apply_migrations(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY)"
        )
        applied = {
            int(row["version"]) for row in conn.execute("SELECT version FROM schema_migrations")
        }
        for version, migration in sorted(SCHEMA_MIGRATIONS, key=lambda item: item[0]):
            if version in applied:
                continue
            migration(conn)
            conn.execute(
                "INSERT INTO schema_migrations (version) VALUES (?)",
                (version,),
            )

    def _backfill_history_cursor_events(self, conn: sqlite3.Connection) -> None:
        rows = conn.execute(
            "SELECT slug, history_cursor, history_changed_at, updated_at, created_at FROM entities"
        ).fetchall()
        now_iso = datetime.now(timezone.utc).isoformat()
        for row in rows:
            cursor = row["history_cursor"]
            if not cursor:
                continue
            changed_at = (
                row["history_changed_at"]
                or row["updated_at"]
                or row["created_at"]
                or now_iso
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO history_cursor_events (entity_slug, history_cursor, changed_at)
                VALUES (?, ?, ?)
                """,
                (row["slug"], cursor, changed_at),
            )

        conn.execute(
            """
            UPDATE history
               SET history_cursor = (
                    SELECT history_cursor FROM entities WHERE entities.slug = history.entity_slug
                )
             WHERE history_cursor IS NULL
            """
        )

    @staticmethod
    def _record_history_cursor_event(
        conn: sqlite3.Connection, slug: str, cursor: Optional[str], changed_at: Optional[str]
    ) -> None:
        if not cursor:
            return
        timestamp = changed_at or datetime.now(timezone.utc).isoformat()
        conn.execute(
            """
            INSERT INTO history_cursor_events (entity_slug, history_cursor, changed_at)
            VALUES (?, ?, ?)
            ON CONFLICT(entity_slug, history_cursor)
            DO UPDATE SET changed_at = excluded.changed_at
            """,
            (slug, cursor, timestamp),
        )

    def _backfill_historic_points(
        self,
        conn: sqlite3.Connection,
        slug: str,
        *,
        cursor: Optional[str] = None,
    ) -> None:
        threshold = datetime.now(timezone.utc) - HISTORICAL_THRESHOLD
        rows = conn.execute(
            """
            SELECT id, measured_at, created_at, history_cursor, is_historic
              FROM history
             WHERE entity_slug = ?
            """,
            (slug,),
        ).fetchall()
        for row in rows:
            measured_raw = row["measured_at"] or row["created_at"]
            try:
                measured_dt = datetime.fromisoformat(measured_raw)
            except (TypeError, ValueError):
                continue
            if measured_dt > threshold:
                continue
            updates: List[str] = []
            params: List[Any] = []
            if not bool(row["is_historic"]):
                updates.append("is_historic = 1")
            if cursor and not row["history_cursor"]:
                updates.append("history_cursor = ?")
                params.append(cursor)
            if not updates:
                continue
            params.append(row["id"])
            conn.execute(
                f"UPDATE history SET {', '.join(updates)} WHERE id = ?",
                tuple(params),
            )

    def _list_history_cursor_events_internal(
        self, conn: sqlite3.Connection, slug: str
    ) -> List[HistoryCursorEvent]:
        rows = conn.execute(
            """
            SELECT history_cursor, changed_at
              FROM history_cursor_events
             WHERE entity_slug = ?
          ORDER BY datetime(changed_at) ASC
            """,
            (slug,),
        ).fetchall()
        events: List[HistoryCursorEvent] = []
        for row in rows:
            changed_at_raw = row["changed_at"]
            try:
                changed_at = datetime.fromisoformat(changed_at_raw)
            except (TypeError, ValueError):
                continue
            events.append(
                HistoryCursorEvent(
                    history_cursor=str(row["history_cursor"]),
                    changed_at=changed_at,
                )
            )
        return events

    def _ensure_entity_history_cursor(
        self,
        conn: sqlite3.Connection,
        slug: str,
        *,
        existing: Optional[str] = None,
        timestamp: Optional[str] = None,
    ) -> str:
        if existing:
            return str(existing)
        row = conn.execute(
            "SELECT history_cursor FROM entities WHERE slug = ?",
            (slug,),
        ).fetchone()
        if row and row["history_cursor"]:
            return str(row["history_cursor"])
        new_cursor = _generate_history_cursor()
        conn.execute(
            """
            UPDATE entities
               SET history_cursor = ?
             WHERE slug = ?
            """,
            (new_cursor, slug),
        )
        self._record_history_cursor_event(conn, slug, new_cursor, timestamp)
        return new_cursor

    @staticmethod
    def _row_to_api_user(row: sqlite3.Row) -> ApiUser:
        keys = set(row.keys())
        return ApiUser(
            id=row["id"],
            name=row["name"],
            token=row["token"],
            is_superuser=bool(row["is_superuser"]) if "is_superuser" in keys else False,
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    @staticmethod
    def _row_to_webhook_subscription(row: sqlite3.Row) -> WebhookSubscription:
        keys = set(row.keys())
        description = row["description"].strip() if row["description"] else ""
        return WebhookSubscription(
            id=row["id"],
            user_id=row["user_id"],
            description=description or None,
            webhook_url=row["webhook_url"],
            secret=row["secret"] or None,
            metadata=_deserialize_metadata(row["metadata"]) if "metadata" in keys else None,
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    @staticmethod
    def _row_to_webhook_target(row: sqlite3.Row) -> WebhookTarget:
        keys = set(row.keys())
        description_raw = row["description"].strip() if row["description"] else ""
        return WebhookTarget(
            id=row["id"],
            user_id=row["user_id"],
            webhook_url=row["webhook_url"],
            secret=row["secret"] or None,
            token=row["token"],
            description=description_raw or None,
            metadata=_deserialize_metadata(row["metadata"]) if "metadata" in keys else None,
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    @staticmethod
    def _row_to_integration_connection(
        row: sqlite3.Row,
    ) -> IntegrationConnectionDetail:
        owner_name = row["api_user_name"] if row["api_user_name"] else "Unnamed API user"
        last_seen_raw = row["last_seen"] if "last_seen" in row.keys() else None
        last_seen = datetime.fromisoformat(last_seen_raw) if last_seen_raw else None
        return IntegrationConnectionDetail(
            id=row["id"],
            api_user_id=row["api_user_id"],
            entry_id=row["entry_id"],
            title=row["title"] or None,
            entity_count=int(row["entity_count"] or 0),
            included_entities=_deserialize_options(row["included_entities"]),
            ignored_entities=_deserialize_options(row["ignored_entities"]),
            metadata=_deserialize_metadata(row["metadata"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            last_seen=last_seen,
            owner=IntegrationConnectionOwner(
                id=row["api_user_id"],
                name=owner_name,
                is_superuser=bool(row["api_user_is_superuser"]),
            ),
        )

    def _migrate_from_json(self) -> None:
        legacy_path = self._db_path.with_suffix(".json")
        if not legacy_path.exists():
            return

        try:
            with legacy_path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return

        entities = data.get("entities") or data.get("inputs", [])
        if not entities:
            return

        with self._connection() as conn:
            existing = conn.execute("SELECT COUNT(*) AS count FROM entities").fetchone()
            if existing and existing["count"]:
                return

            for item in entities:
                try:
                    entity = ManagedEntity(**item)
                except Exception:  # noqa: BLE001
                    continue
                conn.execute(
                    """
                    INSERT OR REPLACE INTO entities (
                        slug, name, entity_id, entity_kind, entity_type, description, default_value,
                        options, last_value, last_measured_at, created_at, updated_at,
                        device_class, unit_of_measurement, component, unique_id, object_id,
                        node_id, state_topic, availability_topic, icon, state_class,
                        force_update, device_name, device_id, device_manufacturer, device_model,
                        device_sw_version, device_identifiers, statistics_mode, ha_enabled
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entity.slug,
                    entity.name,
                    entity.entity_id,
                    entity.type.value,
                    entity.entity_type.value,
                    entity.description,
                    _serialize_value(entity.default_value),
                    _serialize_options(entity.options),
                    _serialize_value(entity.last_value),
                    entity.last_measured_at.isoformat() if entity.last_measured_at else None,
                    entity.created_at.isoformat(),
                    entity.updated_at.isoformat(),
                    entity.device_class,
                    entity.unit_of_measurement,
                    entity.component,
                    entity.unique_id,
                    entity.object_id,
                    entity.node_id,
                    entity.state_topic,
                    entity.availability_topic,
                    entity.icon,
                    entity.state_class,
                    int(entity.force_update),
                    entity.device_name,
                    entity.device_id,
                    entity.device_manufacturer,
                    entity.device_model,
                    entity.device_sw_version,
                    _serialize_identifiers(entity.device_identifiers),
                    entity.statistics_mode.value if entity.statistics_mode else None,
                    int(entity.ha_enabled),
                ),
            )

    def ensure_superuser(self, *, name: str, token: str) -> ApiUser:
        cleaned_name = name.strip() or "Superuser"
        cleaned_token = token.strip()
        if not cleaned_token:
            raise ValueError("Superuser token cannot be blank.")
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._lock:
            with self._connection() as conn:
                row = conn.execute(
                    "SELECT * FROM api_users WHERE token = ?",
                    (cleaned_token,),
                ).fetchone()
                if row is None:
                    conn.execute(
                        """
                        INSERT INTO api_users (name, token, is_superuser, created_at, updated_at)
                        VALUES (?, ?, 1, ?, ?)
                        """,
                        (cleaned_name, cleaned_token, now_iso, now_iso),
                    )
                else:
                    conn.execute(
                        """
                        UPDATE api_users
                           SET name = ?,
                               is_superuser = 1,
                               updated_at = ?
                         WHERE id = ?
                        """,
                        (cleaned_name, now_iso, row["id"]),
                    )
                ensured = conn.execute(
                    "SELECT * FROM api_users WHERE token = ?",
                    (cleaned_token,),
                ).fetchone()
        if ensured is None:
            raise RuntimeError("Unable to ensure superuser token.")
        return self._row_to_api_user(ensured)

    def list_api_users(self) -> List[ApiUser]:
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM api_users ORDER BY is_superuser DESC, name COLLATE NOCASE",
            ).fetchall()
        return [self._row_to_api_user(row) for row in rows]

    def create_api_user(self, payload: ApiUserCreate) -> ApiUser:
        cleaned_name = payload.name.strip()
        cleaned_token = payload.token.strip()
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._lock:
            with self._connection() as conn:
                try:
                    cursor = conn.execute(
                        """
                        INSERT INTO api_users (name, token, is_superuser, created_at, updated_at)
                        VALUES (?, ?, 0, ?, ?)
                        """,
                        (cleaned_name, cleaned_token, now_iso, now_iso),
                    )
                except sqlite3.IntegrityError as exc:
                    if "api_users.token" in str(exc):
                        raise ValueError("API token already exists.") from exc
                    raise
                row = conn.execute(
                    "SELECT * FROM api_users WHERE id = ?",
                    (cursor.lastrowid,),
                ).fetchone()
        if row is None:
            raise RuntimeError("Unable to create API user.")
        return self._row_to_api_user(row)

    def update_api_user(self, user_id: int, payload: ApiUserUpdate) -> ApiUser:
        update_data = payload.model_dump(exclude_unset=True)
        cleaned_name = update_data.get("name")
        cleaned_token = update_data.get("token")
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._lock:
            with self._connection() as conn:
                existing = conn.execute(
                    "SELECT * FROM api_users WHERE id = ?",
                    (user_id,),
                ).fetchone()
                if existing is None:
                    raise KeyError(f"API user {user_id} not found.")
                is_superuser = bool(existing["is_superuser"])
                name_value = cleaned_name if cleaned_name is not None else existing["name"]
                token_value = cleaned_token if cleaned_token is not None else existing["token"]
                if is_superuser and cleaned_token is not None and cleaned_token != existing["token"]:
                    raise ValueError("The superuser token cannot be modified.")
                try:
                    conn.execute(
                        """
                        UPDATE api_users
                           SET name = ?,
                               token = ?,
                               updated_at = ?
                         WHERE id = ?
                        """,
                        (name_value, token_value.strip(), now_iso, user_id),
                    )
                except sqlite3.IntegrityError as exc:
                    if "api_users.token" in str(exc):
                        raise ValueError("API token already exists.") from exc
                    raise
                row = conn.execute(
                    "SELECT * FROM api_users WHERE id = ?",
                    (user_id,),
                ).fetchone()
        if row is None:
            raise RuntimeError("Unable to update API user.")
        return self._row_to_api_user(row)

    def delete_api_user(self, user_id: int) -> None:
        with self._lock:
            with self._connection() as conn:
                existing = conn.execute(
                    "SELECT * FROM api_users WHERE id = ?",
                    (user_id,),
                ).fetchone()
                if existing is None:
                    raise KeyError(f"API user {user_id} not found.")
                if bool(existing["is_superuser"]):
                    raise ValueError("The built-in superuser cannot be removed.")
                conn.execute(
                    "DELETE FROM api_users WHERE id = ?",
                    (user_id,),
                )

    def get_api_user_by_token(self, token: str) -> Optional[ApiUser]:
        cleaned = token.strip()
        if not cleaned:
            return None
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM api_users WHERE token = ?",
                (cleaned,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_api_user(row)

    def list_webhook_subscriptions(self, user_id: Optional[int] = None) -> List[WebhookSubscription]:
        query = "SELECT * FROM webhook_subscriptions"
        params: tuple[Any, ...]
        if user_id is not None:
            query += " WHERE user_id = ?"
            params = (user_id,)
        else:
            params = tuple()
        query += " ORDER BY datetime(created_at) ASC"
        with self._connection() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_webhook_subscription(row) for row in rows]

    def save_webhook_subscription(self, user_id: int, registration: WebhookRegistration) -> WebhookSubscription:
        description_value = (registration.description or "").strip()
        metadata_value = _serialize_metadata(registration.metadata)
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._lock:
            with self._connection() as conn:
                user_row = conn.execute(
                    "SELECT id FROM api_users WHERE id = ?",
                    (user_id,),
                ).fetchone()
                if user_row is None:
                    raise KeyError(f"API user {user_id} not found.")
                existing = conn.execute(
                    "SELECT * FROM webhook_subscriptions WHERE user_id = ? AND description = ?",
                    (user_id, description_value),
                ).fetchone()
                webhook_url_value = str(registration.webhook_url)
                secret_value = registration.secret or None
                if existing is None:
                    cursor = conn.execute(
                        """
                        INSERT INTO webhook_subscriptions (
                            user_id, description, webhook_url, secret, metadata, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            user_id,
                            description_value,
                            webhook_url_value,
                            secret_value,
                            metadata_value,
                            now_iso,
                            now_iso,
                        ),
                    )
                    subscription_id = cursor.lastrowid
                else:
                    conn.execute(
                        """
                        UPDATE webhook_subscriptions
                           SET webhook_url = ?,
                               secret = ?,
                               metadata = ?,
                               updated_at = ?
                         WHERE id = ?
                        """,
                        (
                            webhook_url_value,
                            secret_value,
                            metadata_value,
                            now_iso,
                            existing["id"],
                        ),
                    )
                    subscription_id = existing["id"]
                row = conn.execute(
                    "SELECT * FROM webhook_subscriptions WHERE id = ?",
                    (subscription_id,),
                ).fetchone()
        if row is None:
            raise RuntimeError("Unable to persist webhook subscription.")
        return self._row_to_webhook_subscription(row)

    def delete_webhook_subscription(
        self,
        subscription_id: int,
        *,
        user_id: Optional[int] = None,
    ) -> None:
        query = "DELETE FROM webhook_subscriptions WHERE id = ?"
        params: tuple[Any, ...]
        if user_id is not None:
            query += " AND user_id = ?"
            params = (subscription_id, user_id)
        else:
            params = (subscription_id,)
        with self._lock:
            with self._connection() as conn:
                cursor = conn.execute(query, params)
                if cursor.rowcount == 0:
                    raise KeyError(f"Webhook subscription {subscription_id} not found.")

    def list_webhook_targets(self) -> List[WebhookTarget]:
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT ws.*, u.token
                  FROM webhook_subscriptions AS ws
                  JOIN api_users AS u ON u.id = ws.user_id
                """
            ).fetchall()
        return [self._row_to_webhook_target(row) for row in rows]

    def list_integration_connections(self) -> List[IntegrationConnectionSummary]:
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT ic.*, au.name AS api_user_name, au.is_superuser AS api_user_is_superuser
                  FROM integration_connections AS ic
                  JOIN api_users AS au ON au.id = ic.api_user_id
                 ORDER BY datetime(ic.updated_at) DESC
                """
            ).fetchall()
        return [self._row_to_integration_connection(row) for row in rows]

    def get_integration_connection(self, entry_id: str) -> Optional[IntegrationConnectionDetail]:
        cleaned = entry_id.strip()
        if not cleaned:
            return None
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT ic.*, au.name AS api_user_name, au.is_superuser AS api_user_is_superuser
                  FROM integration_connections AS ic
                  JOIN api_users AS au ON au.id = ic.api_user_id
                 WHERE ic.entry_id = ?
                """,
                (cleaned,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_integration_connection(row)

    def save_integration_connection(
        self,
        user: ApiUser,
        payload: IntegrationConnectionCreate,
    ) -> IntegrationConnectionDetail:
        now_iso = datetime.now(timezone.utc).isoformat()
        last_seen_iso = (
            payload.last_seen.isoformat()
            if payload.last_seen is not None
            else now_iso
        )
        included_value = _serialize_options(payload.included_entities)
        ignored_value = _serialize_options(payload.ignored_entities)
        metadata_value = _serialize_metadata(payload.metadata)
        entity_count_value = int(payload.entity_count or 0)
        with self._lock:
            with self._connection() as conn:
                existing = conn.execute(
                    "SELECT id FROM integration_connections WHERE entry_id = ?",
                    (payload.entry_id,),
                ).fetchone()
                if existing is None:
                    conn.execute(
                        """
                        INSERT INTO integration_connections (
                            api_user_id, entry_id, title, entity_count, included_entities,
                            ignored_entities, metadata, created_at, updated_at, last_seen
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            user.id,
                            payload.entry_id,
                            payload.title,
                            entity_count_value,
                            included_value,
                            ignored_value,
                            metadata_value,
                            now_iso,
                            now_iso,
                            last_seen_iso,
                        ),
                    )
                else:
                    conn.execute(
                        """
                        UPDATE integration_connections
                           SET api_user_id = ?,
                               title = ?,
                               entity_count = ?,
                               included_entities = ?,
                               ignored_entities = ?,
                               metadata = ?,
                               updated_at = ?,
                               last_seen = ?
                         WHERE entry_id = ?
                        """,
                        (
                            user.id,
                            payload.title,
                            entity_count_value,
                            included_value,
                            ignored_value,
                            metadata_value,
                            now_iso,
                            last_seen_iso,
                            payload.entry_id,
                        ),
                    )
                row = conn.execute(
                    """
                    SELECT ic.*, au.name AS api_user_name, au.is_superuser AS api_user_is_superuser
                      FROM integration_connections AS ic
                      JOIN api_users AS au ON au.id = ic.api_user_id
                     WHERE ic.entry_id = ?
                    """,
                    (payload.entry_id,),
                ).fetchone()
        if row is None:
            raise RuntimeError("Unable to persist integration connection.")
        return self._row_to_integration_connection(row)

    def delete_integration_connection(
        self,
        entry_id: str,
        *,
        user_id: Optional[int] = None,
    ) -> None:
        cleaned = entry_id.strip()
        if not cleaned:
            raise ValueError("Provide a valid entry id to delete.")
        query = "DELETE FROM integration_connections WHERE entry_id = ?"
        params: tuple[Any, ...]
        if user_id is not None:
            query += " AND api_user_id = ?"
            params = (cleaned, user_id)
        else:
            params = (cleaned,)
        with self._lock:
            with self._connection() as conn:
                cursor = conn.execute(query, params)
                if cursor.rowcount == 0:
                    raise KeyError(f"Integration connection {cleaned} not found.")

    def list_integration_connection_history(
        self,
        entry_id: str,
        *,
        limit: int = 200,
    ) -> List[IntegrationConnectionHistoryItem]:
        connection = self.get_integration_connection(entry_id)
        if connection is None:
            raise KeyError(f"Integration connection {entry_id} not found.")
        entity_slugs = connection.included_entities or []
        if not entity_slugs:
            return []
        placeholders = ",".join(["?"] * len(entity_slugs))
        query = f"""
            SELECT h.entity_slug, h.value, h.measured_at, h.created_at, h.history_cursor, h.is_historic, he.name
              FROM history AS h
              JOIN entities AS he ON he.slug = h.entity_slug
             WHERE h.entity_slug IN ({placeholders})
             ORDER BY datetime(COALESCE(h.measured_at, h.created_at)) DESC
             LIMIT ?
        """
        params: List[Any] = list(entity_slugs)
        params.append(limit)
        with self._connection() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        history: List[IntegrationConnectionHistoryItem] = []
        for row in rows:
            recorded_at = datetime.fromisoformat(row["created_at"])
            measured_source = row["measured_at"] or row["created_at"]
            try:
                measured_at = datetime.fromisoformat(measured_source) if measured_source else None
            except ValueError:
                measured_at = None
            history.append(
                IntegrationConnectionHistoryItem(
                    entity_slug=row["entity_slug"],
                    entity_name=row["name"],
                    value=_deserialize_value(row["value"]),
                    measured_at=measured_at,
                    historic=bool(row["is_historic"]) if "is_historic" in row.keys() else False,
                    historic_cursor=(
                        str(row["history_cursor"])
                        if "history_cursor" in row.keys() and row["history_cursor"]
                        else None
                    ),
                    recorded_at=recorded_at,
                )
            )
        return history

    def _row_to_entity(self, row: sqlite3.Row) -> ManagedEntity:
        mapping = dict(row)
        keys = set(mapping.keys())
        entity_type_value = mapping.get("entity_type", "mqtt")
        try:
            entity_type = EntityTransportType(entity_type_value or "mqtt")
        except ValueError:
            entity_type = EntityTransportType.MQTT
        is_mqtt = entity_type == EntityTransportType.MQTT
        node_id = mapping.get("node_id") if is_mqtt else None
        slug = mapping["slug"]
        state_topic_value = (
            (mapping.get("state_topic") or "").strip() if is_mqtt else None
        )
        availability_topic_value = (
            (mapping.get("availability_topic") or "").strip() if is_mqtt else None
        )
        if is_mqtt:
            if not state_topic_value:
                state_topic_value = f"{slug}/state"
            if not availability_topic_value:
                availability_topic_value = f"{slug}/availability"
        force_update_value = bool(mapping.get("force_update", 1)) if is_mqtt else False
        device_manufacturer = mapping.get("device_manufacturer") if is_mqtt else None
        device_model = mapping.get("device_model") if is_mqtt else None
        device_sw_version = mapping.get("device_sw_version") if is_mqtt else None
        identifiers = (
            _deserialize_identifiers(mapping.get("device_identifiers"))
            if is_mqtt
            else []
        )
        statistics_mode_value = mapping.get("statistics_mode")
        statistics_mode = None
        if entity_type == EntityTransportType.HASSEMS:
            try:
                statistics_mode = HASSEMSStatisticsMode(
                    statistics_mode_value or HASSEMSStatisticsMode.LINEAR
                )
            except ValueError:
                statistics_mode = HASSEMSStatisticsMode.LINEAR

        history_cursor = mapping.get("history_cursor") or None
        with self._connection() as entity_conn:
            if not history_cursor:
                history_cursor = self._ensure_entity_history_cursor(
                    entity_conn,
                    slug,
                    timestamp=mapping.get("updated_at") or mapping.get("created_at"),
                )
            cursor_events = self._list_history_cursor_events_internal(entity_conn, slug)
        history_changed_at_raw = mapping.get("history_changed_at")
        history_changed_at = None
        if history_changed_at_raw:
            try:
                history_changed_at = datetime.fromisoformat(history_changed_at_raw)
            except ValueError:
                history_changed_at = None

        entity_kind_raw = mapping["entity_kind"]
        try:
            entity_kind = (
                entity_kind_raw
                if isinstance(entity_kind_raw, EntityKind)
                else EntityKind(str(entity_kind_raw))
            )
        except ValueError:
            entity_kind = EntityKind.INPUT_TEXT

        return ManagedEntity(
            slug=mapping["slug"],
            name=mapping["name"],
            entity_id=mapping["entity_id"],
            type=entity_kind,
            entity_type=entity_type,
            description=mapping["description"],
            default_value=_deserialize_value(mapping["default_value"]),
            options=_deserialize_options(mapping["options"]),
            last_value=_deserialize_value(mapping["last_value"]),
            last_measured_at=datetime.fromisoformat(mapping["last_measured_at"])
            if "last_measured_at" in keys and mapping["last_measured_at"]
            else None,
            created_at=datetime.fromisoformat(mapping["created_at"]),
            updated_at=datetime.fromisoformat(mapping["updated_at"]),
            device_class=mapping["device_class"],
            unit_of_measurement=mapping["unit_of_measurement"],
            component=mapping.get("component", "sensor"),
            unique_id=mapping.get("unique_id", mapping["slug"]),
            object_id=mapping.get("object_id", mapping["slug"]),
            node_id=node_id,
            state_topic=state_topic_value,
            availability_topic=availability_topic_value,
            icon=mapping.get("icon"),
            state_class=mapping.get("state_class"),
            force_update=force_update_value,
            device_name=mapping.get("device_name", mapping["name"]),
            device_id=mapping.get("device_id", slugify_identifier(mapping.get("device_name", ""))),
            device_manufacturer=device_manufacturer,
            device_model=device_model,
            device_sw_version=device_sw_version,
            device_identifiers=identifiers,
            statistics_mode=statistics_mode,
            history_cursor=history_cursor,
            history_cursor_events=cursor_events,
            history_changed_at=history_changed_at,
            ha_enabled=bool(mapping.get("ha_enabled", 1)),
        )

    def list_entities(self) -> List[ManagedEntity]:
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM entities ORDER BY name COLLATE NOCASE"
            ).fetchall()
        return [self._row_to_entity(row) for row in rows]

    def list_entities_by_kind(
        self, entity_type: EntityTransportType, *, only_enabled: bool = False
    ) -> List[ManagedEntity]:
        with self._connection() as conn:
            query = "SELECT * FROM entities WHERE entity_type = ?"
            params: List[Any] = [entity_type.value]
            if only_enabled:
                query += " AND ha_enabled = 1"
            query += " ORDER BY name COLLATE NOCASE"
            rows = conn.execute(query, tuple(params)).fetchall()
        return [self._row_to_entity(row) for row in rows]

    def get_entity(self, slug: str) -> Optional[ManagedEntityRecord]:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM entities WHERE slug = ?",
                (slug,),
            ).fetchone()
        if row is None:
            return None
        return ManagedEntityRecord(self._row_to_entity(row))

    def create_entity(self, payload: ManagedEntityCreate) -> ManagedEntity:
        record = ManagedEntityRecord.create(payload)
        entity = record.entity

        with self._lock:
            if self.get_entity(entity.slug) is not None:
                raise ValueError(f"Entity with slug '{entity.slug}' already exists.")
            with self._connection() as conn:
                conn.execute(
                    """
                    INSERT INTO entities (
                        slug, name, entity_id, entity_kind, entity_type, description, default_value,
                        options, last_value, last_measured_at, created_at, updated_at,
                        device_class, unit_of_measurement, component, unique_id, object_id,
                        node_id, state_topic, availability_topic, icon, state_class,
                        force_update, device_name, device_id, device_manufacturer, device_model,
                        device_sw_version, device_identifiers, statistics_mode, ha_enabled, history_cursor,
                        history_changed_at
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                    """,
                    (
                        entity.slug,
                        entity.name,
                        entity.entity_id,
                        entity.type.value,
                        entity.entity_type.value,
                        entity.description,
                        _serialize_value(entity.default_value),
                        _serialize_options(entity.options),
                        _serialize_value(entity.last_value),
                        entity.last_measured_at.isoformat() if entity.last_measured_at else None,
                        entity.created_at.isoformat(),
                        entity.updated_at.isoformat(),
                        entity.device_class,
                        entity.unit_of_measurement,
                        entity.component,
                        entity.unique_id,
                        entity.object_id,
                        entity.node_id,
                        entity.state_topic or "",
                        entity.availability_topic or "",
                        entity.icon,
                        entity.state_class,
                        int(entity.force_update),
                        entity.device_name,
                        entity.device_id,
                        entity.device_manufacturer,
                        entity.device_model,
                        entity.device_sw_version,
                        _serialize_identifiers(entity.device_identifiers),
                        entity.statistics_mode.value if entity.statistics_mode else None,
                        int(entity.ha_enabled),
                        entity.history_cursor,
                        entity.history_changed_at.isoformat()
                        if entity.history_changed_at
                        else None,
                    ),
                )
                if entity.entity_type == EntityTransportType.HASSEMS:
                    self._record_history_cursor_event(
                        conn,
                        entity.slug,
                        entity.history_cursor,
                        entity.created_at.isoformat(),
                    )
        return entity

    def update_entity(self, slug: str, payload: ManagedEntityUpdate) -> ManagedEntity:
        with self._lock:
            existing = self.get_entity(slug)
            if existing is None:
                raise KeyError(f"Entity '{slug}' not found.")
            existing.update(payload)
            entity = existing.entity
            with self._connection() as conn:
                conn.execute(
                    """
                    UPDATE entities
                       SET name = ?,
                           entity_id = ?,
                           entity_type = ?,
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
                           device_id = ?,
                           device_manufacturer = ?,
                           device_model = ?,
                           device_sw_version = ?,
                           device_identifiers = ?,
                           statistics_mode = ?,
                           ha_enabled = ?
                     WHERE slug = ?
                    """,
                    (
                        entity.name,
                        entity.entity_id,
                        entity.entity_type.value,
                        entity.description,
                        _serialize_value(entity.default_value),
                        _serialize_options(entity.options),
                        _serialize_value(entity.last_value),
                        entity.last_measured_at.isoformat() if entity.last_measured_at else None,
                        entity.updated_at.isoformat(),
                        entity.device_class,
                        entity.unit_of_measurement,
                        entity.component,
                        entity.unique_id,
                        entity.object_id,
                        entity.node_id,
                        entity.state_topic or "",
                        entity.availability_topic or "",
                        entity.icon,
                        entity.state_class,
                        int(entity.force_update),
                        entity.device_name,
                        entity.device_id,
                        entity.device_manufacturer,
                        entity.device_model,
                        entity.device_sw_version,
                        _serialize_identifiers(entity.device_identifiers),
                        entity.statistics_mode.value if entity.statistics_mode else None,
                        int(entity.ha_enabled),
                        entity.slug,
                    ),
                )
                if entity.entity_type == EntityTransportType.HASSEMS:
                    self._record_history_cursor_event(
                        conn,
                        entity.slug,
                        entity.history_cursor,
                        entity.created_at.isoformat(),
                    )
        return entity

    def delete_entity(self, slug: str) -> None:
        with self._lock:
            with self._connection() as conn:
                cursor = conn.execute(
                    "DELETE FROM entities WHERE slug = ?",
                    (slug,),
                )
                if cursor.rowcount == 0:
                    raise KeyError(f"Entity '{slug}' not found.")

    def set_last_value(self, slug: str, value: InputValue, *, measured_at: datetime) -> ManagedEntity:
        timestamp = datetime.now(timezone.utc).isoformat()
        measured_iso = measured_at.astimezone(timezone.utc).isoformat()
        serialized_value = _serialize_value(value)
        is_historical = _is_historical_timestamp(measured_at)
        with self._lock:
            with self._connection() as conn:
                entity_row = conn.execute(
                    "SELECT history_cursor, last_measured_at FROM entities WHERE slug = ?",
                    (slug,),
                ).fetchone()
                if entity_row is None:
                    raise KeyError(f"Entity '{slug}' not found.")
                existing_cursor = entity_row["history_cursor"] if entity_row else None
                existing_last_measured_raw = (
                    entity_row["last_measured_at"] if entity_row else None
                )
                existing_last_measured: Optional[datetime] = None
                if existing_last_measured_raw:
                    try:
                        existing_last_measured = datetime.fromisoformat(
                            existing_last_measured_raw
                        )
                    except ValueError:
                        existing_last_measured = None
                    if existing_last_measured and existing_last_measured.tzinfo is None:
                        existing_last_measured = existing_last_measured.replace(
                            tzinfo=timezone.utc
                        )
                incoming_measured = measured_at.astimezone(timezone.utc)
                should_update_last = (
                    existing_last_measured is None
                    or incoming_measured >= existing_last_measured.astimezone(timezone.utc)
                )
                if is_historical:
                    history_cursor_value = self._touch_history_cursor(
                        conn,
                        slug,
                        timestamp=timestamp,
                    )
                else:
                    history_cursor_value = self._ensure_entity_history_cursor(
                        conn,
                        slug,
                        existing=existing_cursor,
                        timestamp=timestamp,
                    )
                if should_update_last:
                    cursor = conn.execute(
                        """
                        UPDATE entities
                           SET last_value = ?,
                               last_measured_at = ?,
                               updated_at = ?
                         WHERE slug = ?
                        """,
                        (serialized_value, measured_iso, timestamp, slug),
                    )
                else:
                    cursor = conn.execute(
                        """
                        UPDATE entities
                           SET updated_at = ?
                         WHERE slug = ?
                        """,
                        (timestamp, slug),
                    )
                if cursor.rowcount == 0:
                    raise KeyError(f"Entity '{slug}' not found.")
                conn.execute(
                    """
                    INSERT INTO history (
                        entity_slug, value, measured_at, created_at, history_cursor, is_historic
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        slug,
                        serialized_value,
                        measured_iso,
                        timestamp,
                        history_cursor_value,
                        int(is_historical),
                    ),
                )
                if is_historical:
                    self._backfill_historic_points(
                        conn,
                        slug,
                        cursor=history_cursor_value,
                    )
                row = conn.execute(
                    "SELECT * FROM entities WHERE slug = ?",
                    (slug,),
                ).fetchone()
        if row is None:
            raise KeyError(f"Entity '{slug}' not found.")
        return self._row_to_entity(row)

    def list_history(self, slug: str, limit: int = 200) -> List[HistoryPoint]:
        query = (
            """
            SELECT id, value, measured_at, created_at, history_cursor, is_historic
              FROM history
             WHERE entity_slug = ?
          ORDER BY datetime(COALESCE(measured_at, created_at)) ASC,
                   datetime(created_at) ASC
            """
        )
        params: List[Any] = [slug]
        if limit > 0:
            query += " LIMIT ?"
            params.append(limit)
        with self._connection() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        history: List[HistoryPoint] = []
        for row in rows:
            point = self._row_to_history_point(row)
            if point is not None:
                history.append(point)
        return history

    def list_history_cursor_events(self, slug: str) -> List[HistoryCursorEvent]:
        with self._connection() as conn:
            return self._list_history_cursor_events_internal(conn, slug)

    def update_history_point(
        self,
        slug: str,
        history_id: int,
        payload: HistoryPointUpdate,
    ) -> HistoryPoint:
        measured_iso = (
            payload.measured_at.astimezone(timezone.utc).isoformat()
            if payload.measured_at is not None
            else None
        )
        serialized_value = _serialize_value(payload.value)
        if serialized_value is None:
            raise ValueError("History value cannot be null.")
        with self._lock:
            with self._connection() as conn:
                existing_row = conn.execute(
                    """
                    SELECT measured_at, created_at, history_cursor
                      FROM history
                     WHERE id = ?
                       AND entity_slug = ?
                    """,
                    (history_id, slug),
                ).fetchone()
                if existing_row is None:
                    raise KeyError(f"History entry {history_id} not found for entity '{slug}'.")
                try:
                    previous_measured = existing_row["measured_at"] or existing_row["created_at"]
                    previous_dt = datetime.fromisoformat(previous_measured)
                except (TypeError, ValueError):
                    previous_dt = None
                new_dt = payload.measured_at or previous_dt

                requires_new_cursor = _is_historical_timestamp(previous_dt) or _is_historical_timestamp(new_dt)
                change_timestamp = datetime.now(timezone.utc).isoformat()
                is_historic_flag = _is_historical_timestamp(new_dt)
                if requires_new_cursor:
                    history_cursor_value = self._touch_history_cursor(
                        conn,
                        slug,
                        timestamp=change_timestamp,
                    )
                else:
                    history_cursor_value = self._ensure_entity_history_cursor(
                        conn,
                        slug,
                        existing=existing_row["history_cursor"],
                        timestamp=change_timestamp,
                    )

                cursor = conn.execute(
                    """
                    UPDATE history
                       SET value = ?,
                           measured_at = ?,
                           history_cursor = ?,
                           is_historic = ?
                     WHERE id = ?
                       AND entity_slug = ?
                    """,
                    (
                        serialized_value,
                        measured_iso,
                        history_cursor_value,
                        int(is_historic_flag),
                        history_id,
                        slug,
                    ),
                )
                if cursor.rowcount == 0:
                    raise KeyError(f"History entry {history_id} not found for entity '{slug}'.")
                if requires_new_cursor or is_historic_flag:
                    self._backfill_historic_points(
                        conn,
                        slug,
                        cursor=history_cursor_value,
                    )
                row = conn.execute(
                    """
                    SELECT id, value, measured_at, created_at, history_cursor, is_historic
                      FROM history
                     WHERE id = ?
                       AND entity_slug = ?
                    """,
                    (history_id, slug),
                ).fetchone()
                self._sync_entity_last_value(conn, slug)
        if row is None:
            raise KeyError(f"History entry {history_id} not found for entity '{slug}'.")
        point = self._row_to_history_point(row)
        if point is None:
            raise ValueError("History value could not be deserialized.")
        return point

    def delete_history_point(self, slug: str, history_id: int) -> None:
        with self._lock:
            with self._connection() as conn:
                existing_row = conn.execute(
                    """
                    SELECT measured_at, created_at
                      FROM history
                     WHERE id = ?
                       AND entity_slug = ?
                    """,
                    (history_id, slug),
                ).fetchone()
                if existing_row is None:
                    raise KeyError(f"History entry {history_id} not found for entity '{slug}'.")
                try:
                    previous_measured = existing_row["measured_at"] or existing_row["created_at"]
                    previous_dt = datetime.fromisoformat(previous_measured)
                except (TypeError, ValueError):
                    previous_dt = None
                cursor = conn.execute(
                    "DELETE FROM history WHERE id = ? AND entity_slug = ?",
                    (history_id, slug),
                )
                if cursor.rowcount == 0:
                    raise KeyError(f"History entry {history_id} not found for entity '{slug}'.")
                self._sync_entity_last_value(conn, slug)
                new_cursor = None
                if _is_historical_timestamp(previous_dt):
                    timestamp = datetime.now(timezone.utc).isoformat()
                    new_cursor = self._touch_history_cursor(
                        conn, slug, timestamp=timestamp
                    )
                if new_cursor:
                    self._backfill_historic_points(
                        conn,
                        slug,
                        cursor=new_cursor,
                    )

    def _row_to_history_point(self, row: sqlite3.Row) -> Optional[HistoryPoint]:
        if row is None:
            return None
        value = _deserialize_value(row["value"])
        if value is None:
            return None
        # recorded_at is diagnostic-only; measured_at drives all logic.
        recorded_at = datetime.fromisoformat(row["created_at"])
        measured_source = row["measured_at"] or row["created_at"]
        measured_at = datetime.fromisoformat(measured_source)
        history_cursor = row["history_cursor"] if "history_cursor" in row.keys() else None
        if history_cursor is not None:
            history_cursor = str(history_cursor)
        is_historic = bool(row["is_historic"]) if "is_historic" in row.keys() else False
        return HistoryPoint(
            id=row["id"],
            measured_at=measured_at,
            recorded_at=recorded_at,
            value=value,
            historic=is_historic,
            historic_cursor=history_cursor,
            history_cursor=history_cursor,
        )

    def _sync_entity_last_value(self, conn: sqlite3.Connection, slug: str) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        latest = conn.execute(
            """
            SELECT value, measured_at, created_at
              FROM history
             WHERE entity_slug = ?
          ORDER BY datetime(COALESCE(measured_at, created_at)) DESC
             LIMIT 1
            """,
            (slug,),
        ).fetchone()
        if latest is None:
            conn.execute(
                """
                UPDATE entities
                   SET last_value = NULL,
                       last_measured_at = NULL,
                       updated_at = ?
                 WHERE slug = ?
                """,
                (now_iso, slug),
            )
            return
        measured_source = latest["measured_at"] or latest["created_at"]
        conn.execute(
            """
            UPDATE entities
               SET last_value = ?,
                   last_measured_at = ?,
                   updated_at = ?
             WHERE slug = ?
            """,
            (
                latest["value"],
                measured_source,
                now_iso,
                slug,
            ),
        )

    def _touch_history_cursor(
        self,
        conn: sqlite3.Connection,
        slug: str,
        *,
        timestamp: Optional[str] = None,
    ) -> str:
        new_cursor = _generate_history_cursor()
        change_ts = timestamp or datetime.now(timezone.utc).isoformat()
        conn.execute(
            """
            UPDATE entities
               SET history_cursor = ?,
                   history_changed_at = ?
             WHERE slug = ?
            """,
            (new_cursor, change_ts, slug),
        )
        self._record_history_cursor_event(conn, slug, new_cursor, change_ts)
        return new_cursor

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


__all__ = ["ManagedEntityStore", "HISTORICAL_THRESHOLD"]
