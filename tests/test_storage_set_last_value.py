from __future__ import annotations

from datetime import datetime, timedelta, timezone

from services.hassems.models import EntityTransportType, EntityKind
from services.hassems.storage import ManagedEntityStore


def _create_store_with_entity(tmp_path):
    db_path = tmp_path / "hassems.sqlite3"
    store = ManagedEntityStore(db_path)

    slug = "test_height"
    now_iso = datetime.now(timezone.utc).isoformat()
    history_cursor = "cursor-test"

    with store._connection() as conn:  # type: ignore[attr-defined]
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
                slug,
                "Test Height",
                "input_number.test_height",
                EntityKind.INPUT_NUMBER.value,
                EntityTransportType.HASSEMS.value,
                None,
                None,
                None,
                None,
                None,
                now_iso,
                now_iso,
                None,
                "in",
                "sensor",
                slug,
                slug,
                None,
                "",
                "",
                None,
                None,
                0,
                "Test Device",
                "test_device",
                None,
                None,
                None,
                "[]",
                "linear",
                1,
                history_cursor,
                None,
            ),
        )
        store._record_history_cursor_event(  # type: ignore[attr-defined]
            conn,
            slug,
            history_cursor,
            now_iso,
        )

    record = store.get_entity(slug)
    assert record is not None
    return store, record.entity


def test_set_last_value_does_not_overwrite_with_older_measurements(tmp_path):
    store, entity = _create_store_with_entity(tmp_path)

    recent_measurement = datetime.now(timezone.utc)
    store.set_last_value(entity.slug, 12, measured_at=recent_measurement)

    older_measurement = recent_measurement - timedelta(days=4)
    store.set_last_value(entity.slug, 5, measured_at=older_measurement)

    updated_record = store.get_entity(entity.slug)
    assert updated_record is not None
    updated_entity = updated_record.entity

    assert updated_entity.last_value == 12
    assert updated_entity.last_measured_at == recent_measurement

    history = store.list_history(entity.slug)
    assert [point.value for point in history] == [5, 12]
    assert [point.historic for point in history] == [False, False]


def test_set_last_value_marks_historic_without_overwriting_recent(tmp_path):
    store, entity = _create_store_with_entity(tmp_path)

    recent_measurement = datetime.now(timezone.utc)
    store.set_last_value(entity.slug, 42, measured_at=recent_measurement)

    historic_measurement = recent_measurement - timedelta(days=30)
    store.set_last_value(entity.slug, 7, measured_at=historic_measurement)

    updated_record = store.get_entity(entity.slug)
    assert updated_record is not None
    updated_entity = updated_record.entity

    assert updated_entity.last_value == 42
    assert updated_entity.last_measured_at == recent_measurement

    history = store.list_history(entity.slug)
    assert len(history) == 2
    assert history[0].value == 7
    assert history[0].historic is True
    assert history[0].historic_cursor is not None
    assert history[1].value == 42
    assert history[1].historic is False
