from __future__ import annotations

from datetime import datetime, timedelta, timezone

from services.hassems.models import EntityTransportType, HelperType
from services.hassems.storage import InputHelperStore


def _create_store_with_helper(tmp_path):
    db_path = tmp_path / "hassems.sqlite3"
    store = InputHelperStore(db_path)

    slug = "test_height"
    now_iso = datetime.now(timezone.utc).isoformat()
    history_cursor = "cursor-test"

    with store._connection() as conn:  # type: ignore[attr-defined]
        conn.execute(
            """
            INSERT INTO helpers (
                slug, name, entity_id, helper_type, entity_type, description, default_value,
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
                HelperType.INPUT_NUMBER.value,
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

    record = store.get_helper(slug)
    assert record is not None
    return store, record.helper


def test_set_last_value_does_not_overwrite_with_older_measurements(tmp_path):
    store, helper = _create_store_with_helper(tmp_path)

    recent_measurement = datetime.now(timezone.utc)
    store.set_last_value(helper.slug, 12, measured_at=recent_measurement)

    older_measurement = recent_measurement - timedelta(days=4)
    store.set_last_value(helper.slug, 5, measured_at=older_measurement)

    updated_record = store.get_helper(helper.slug)
    assert updated_record is not None
    updated_helper = updated_record.helper

    assert updated_helper.last_value == 12
    assert updated_helper.last_measured_at == recent_measurement

    history = store.list_history(helper.slug)
    assert [point.value for point in history] == [5, 12]
    assert [point.historic for point in history] == [False, False]


def test_set_last_value_marks_historic_without_overwriting_recent(tmp_path):
    store, helper = _create_store_with_helper(tmp_path)

    recent_measurement = datetime.now(timezone.utc)
    store.set_last_value(helper.slug, 42, measured_at=recent_measurement)

    historic_measurement = recent_measurement - timedelta(days=30)
    store.set_last_value(helper.slug, 7, measured_at=historic_measurement)

    updated_record = store.get_helper(helper.slug)
    assert updated_record is not None
    updated_helper = updated_record.helper

    assert updated_helper.last_value == 42
    assert updated_helper.last_measured_at == recent_measurement

    history = store.list_history(helper.slug)
    assert len(history) == 2
    assert history[0].value == 7
    assert history[0].historic is True
    assert history[0].historic_cursor is not None
    assert history[1].value == 42
    assert history[1].historic is False
