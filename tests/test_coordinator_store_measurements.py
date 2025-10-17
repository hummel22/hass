from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest
from unittest.mock import AsyncMock

from custom_components.hassems.coordinator import HASSEMSCoordinator


class DummyConfigEntry:
    def __init__(self) -> None:
        self.data: Dict[str, Any] = {}
        self.options: Dict[str, Any] = {}
        self.entry_id = "entry"


@pytest.mark.asyncio
async def test_store_measurements_today_uses_recorder(monkeypatch: pytest.MonkeyPatch) -> None:
    from homeassistant.core import HomeAssistant

    hass = HomeAssistant(asyncio.get_running_loop())
    recorder_instance = SimpleNamespace(is_running=True)

    monkeypatch.setattr(
        "custom_components.hassems.coordinator.recorder.get_instance",
        lambda hass: recorder_instance,
    )
    monkeypatch.setattr(
        "custom_components.hassems.coordinator.recorder.is_entity_recorded",
        lambda hass, entity_id: True,
    )

    direct_calls: List[Any] = []

    def fake_write(
        instance: Any,
        entity_id: str,
        entries: List[Dict[str, Any]],
        states_only: bool = False,
    ) -> None:
        direct_calls.append((entries, states_only))

    async def fake_add_executor_job(func: Any, *args: Any) -> None:
        func(*args)

    coordinator = HASSEMSCoordinator(hass, client=AsyncMock(), entry=DummyConfigEntry())
    coordinator._entities["test"] = {
        "slug": "test",
        "entity_type": "hassems",
        "unit_of_measurement": "kWh",
    }
    coordinator.register_entity("test", "sensor.test")
    coordinator._recorded_measurements["test"] = {}
    monkeypatch.setattr(
        coordinator,
        "_async_update_statistics",
        AsyncMock(),
    )
    monkeypatch.setattr(coordinator, "_write_measurements_direct", fake_write)
    monkeypatch.setattr(hass, "async_add_executor_job", fake_add_executor_job)

    measured = datetime.now(timezone.utc)
    await coordinator._async_store_measurements(
        "test",
        [
            {
                "measured_at": measured.isoformat(),
                "recorded_at": measured.isoformat(),
                "value": 42,
            }
        ],
    )

    assert not direct_calls, "Fresh measurements should not bypass the recorder"
    coordinator._async_update_statistics.assert_not_called()


@pytest.mark.asyncio
async def test_store_measurements_recent_states_only(monkeypatch: pytest.MonkeyPatch) -> None:
    from homeassistant.core import HomeAssistant

    hass = HomeAssistant(asyncio.get_running_loop())
    recorder_instance = SimpleNamespace(is_running=True)

    monkeypatch.setattr(
        "custom_components.hassems.coordinator.recorder.get_instance",
        lambda hass: recorder_instance,
    )
    monkeypatch.setattr(
        "custom_components.hassems.coordinator.recorder.is_entity_recorded",
        lambda hass, entity_id: True,
    )

    direct_calls: List[Any] = []

    def fake_write(
        instance: Any,
        entity_id: str,
        entries: List[Dict[str, Any]],
        states_only: bool = False,
    ) -> None:
        direct_calls.append((entries, states_only))

    async def fake_add_executor_job(func: Any, *args: Any) -> None:
        func(*args)

    coordinator = HASSEMSCoordinator(hass, client=AsyncMock(), entry=DummyConfigEntry())
    coordinator._entities["test"] = {
        "slug": "test",
        "entity_type": "hassems",
        "unit_of_measurement": "kWh",
    }
    coordinator.register_entity("test", "sensor.test")
    coordinator._recorded_measurements["test"] = {}
    monkeypatch.setattr(
        coordinator,
        "_async_update_statistics",
        AsyncMock(),
    )
    monkeypatch.setattr(coordinator, "_write_measurements_direct", fake_write)
    monkeypatch.setattr(hass, "async_add_executor_job", fake_add_executor_job)

    measured = datetime.now(timezone.utc) - timedelta(days=2)
    await coordinator._async_store_measurements(
        "test",
        [
            {
                "measured_at": measured.isoformat(),
                "recorded_at": (datetime.now(timezone.utc)).isoformat(),
                "value": 5,
            }
        ],
    )

    assert direct_calls, "Expected to write recent history into states"
    entries, states_only_flag = direct_calls[0]
    assert states_only_flag is True
    assert entries[0]["timestamp"] == measured
    assert coordinator._async_update_statistics.await_count == 1


@pytest.mark.asyncio
async def test_store_measurements_accepts_number_entities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from homeassistant.core import HomeAssistant

    hass = HomeAssistant(asyncio.get_running_loop())
    recorder_instance = SimpleNamespace(is_running=True)

    monkeypatch.setattr(
        "custom_components.hassems.coordinator.recorder.get_instance",
        lambda hass: recorder_instance,
    )
    monkeypatch.setattr(
        "custom_components.hassems.coordinator.recorder.is_entity_recorded",
        lambda hass, entity_id: True,
    )

    direct_calls: List[Any] = []

    def fake_write(
        instance: Any,
        entity_id: str,
        entries: List[Dict[str, Any]],
        states_only: bool = False,
    ) -> None:
        direct_calls.append((entries, states_only))

    async def fake_add_executor_job(func: Any, *args: Any) -> None:
        func(*args)

    coordinator = HASSEMSCoordinator(hass, client=AsyncMock(), entry=DummyConfigEntry())
    coordinator._entities["test"] = {
        "slug": "test",
        "entity_type": "hassems",
        "unit_of_measurement": "kWh",
    }
    coordinator.register_entity("test", "number.test")
    coordinator._recorded_measurements["test"] = {}
    stats_mock = AsyncMock()
    monkeypatch.setattr(
        coordinator,
        "_async_update_statistics",
        stats_mock,
    )
    monkeypatch.setattr(coordinator, "_write_measurements_direct", fake_write)
    monkeypatch.setattr(hass, "async_add_executor_job", fake_add_executor_job)

    measured = datetime.now(timezone.utc) - timedelta(days=2)
    await coordinator._async_store_measurements(
        "test",
        [
            {
                "measured_at": measured.isoformat(),
                "recorded_at": (datetime.now(timezone.utc)).isoformat(),
                "value": 5,
            }
        ],
    )

    assert stats_mock.await_count == 1
    assert direct_calls, "Expected number entities to write via recorder"


@pytest.mark.asyncio
async def test_store_measurements_historic_statistics_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from homeassistant.core import HomeAssistant

    hass = HomeAssistant(asyncio.get_running_loop())
    recorder_instance = SimpleNamespace(is_running=True)

    monkeypatch.setattr(
        "custom_components.hassems.coordinator.recorder.get_instance",
        lambda hass: recorder_instance,
    )
    monkeypatch.setattr(
        "custom_components.hassems.coordinator.recorder.is_entity_recorded",
        lambda hass, entity_id: True,
    )

    direct_calls: List[Any] = []

    def fake_write(
        instance: Any,
        entity_id: str,
        entries: List[Dict[str, Any]],
        states_only: bool = False,
    ) -> None:
        direct_calls.append((entries, states_only))

    async def fake_add_executor_job(func: Any, *args: Any) -> None:
        func(*args)

    coordinator = HASSEMSCoordinator(hass, client=AsyncMock(), entry=DummyConfigEntry())
    coordinator._entities["test"] = {
        "slug": "test",
        "entity_type": "hassems",
        "unit_of_measurement": "kWh",
    }
    coordinator.register_entity("test", "sensor.test")
    coordinator._recorded_measurements["test"] = {}
    stats_mock = AsyncMock()
    monkeypatch.setattr(
        coordinator,
        "_async_update_statistics",
        stats_mock,
    )
    monkeypatch.setattr(coordinator, "_write_measurements_direct", fake_write)
    monkeypatch.setattr(hass, "async_add_executor_job", fake_add_executor_job)

    measured = datetime.now(timezone.utc) - timedelta(days=20)
    await coordinator._async_store_measurements(
        "test",
        [
            {
                "measured_at": measured.isoformat(),
                "recorded_at": (datetime.now(timezone.utc)).isoformat(),
                "value": 9,
            }
        ],
    )

    assert not direct_calls, "Historic values should not create state rows"
    assert stats_mock.await_count == 1


@pytest.mark.asyncio
async def test_register_entity_backfills_existing_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from homeassistant.core import HomeAssistant

    hass = HomeAssistant(asyncio.get_running_loop())
    coordinator = HASSEMSCoordinator(hass, client=AsyncMock(), entry=DummyConfigEntry())
    slug = "system-test-1"
    coordinator._history[slug] = [
        {
            "measured_at": datetime.now(timezone.utc).isoformat(),
            "value": 1,
        }
    ]

    store_mock = AsyncMock()
    monkeypatch.setattr(coordinator, "_async_store_measurements", store_mock)

    created_tasks: list[asyncio.Task] = []

    def fake_async_create_task(coro):
        task = hass.loop.create_task(coro)
        created_tasks.append(task)
        return task

    monkeypatch.setattr(hass, "async_create_task", fake_async_create_task, raising=False)

    coordinator.register_entity(slug, "number.system_test_1")

    if created_tasks:
        await asyncio.gather(*created_tasks)

    store_mock.assert_awaited_once_with(slug, coordinator._history[slug], force=True)


@pytest.mark.asyncio
async def test_point_statistics_fill_missing_hours() -> None:
    from homeassistant.core import HomeAssistant

    hass = HomeAssistant(asyncio.get_running_loop())
    coordinator = HASSEMSCoordinator(hass, client=AsyncMock(), entry=DummyConfigEntry())

    base = datetime(2024, 3, 10, 0, 15, tzinfo=timezone.utc)
    history = [
        {"measured_at": base.isoformat(), "value": 5},
        {
            "measured_at": (base + timedelta(hours=3, minutes=5)).isoformat(),
            "value": 7,
        },
    ]

    points = coordinator._parse_measurement_points(history)
    statistics = coordinator._calculate_hourly_statistics(points, "point")

    assert len(statistics) == 4
    starts = [item["start"] for item in statistics]
    assert starts[0] == base.replace(minute=0, second=0, microsecond=0)
    assert starts[-1] == (base + timedelta(hours=3)).replace(
        minute=0, second=0, microsecond=0
    )

    stat_map = {item["start"]: item for item in statistics}
    gap_hour = base.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    zero_stat = stat_map[gap_hour]
    assert zero_stat["mean"] == 0.0
    assert zero_stat["min"] == 0.0
    assert zero_stat["max"] == 0.0
    assert zero_stat["state"] == 0.0

    first_hour = stat_map[starts[0]]
    assert first_hour["mean"] == 5.0
    assert first_hour["min"] == 5.0
    assert first_hour["max"] == 5.0
    assert first_hour["state"] == 5


@pytest.mark.asyncio
async def test_linear_statistics_interpolate_full_window() -> None:
    from homeassistant.core import HomeAssistant

    hass = HomeAssistant(asyncio.get_running_loop())
    coordinator = HASSEMSCoordinator(hass, client=AsyncMock(), entry=DummyConfigEntry())

    base = datetime(2024, 5, 1, 0, 0, tzinfo=timezone.utc)
    history = [
        {"measured_at": base.isoformat(), "value": 0},
        {"measured_at": (base + timedelta(hours=2)).isoformat(), "value": 20},
    ]

    points = coordinator._parse_measurement_points(history)
    window_end = base + timedelta(hours=4)
    statistics = coordinator._calculate_hourly_statistics(
        points,
        "linear",
        history_window=(base, window_end),
    )

    assert len(statistics) == 4
    starts = [item["start"] for item in statistics]
    assert starts == [
        base + timedelta(hours=offset)
        for offset in range(4)
    ]

    stat_map = {item["start"]: item for item in statistics}
    first_hour = stat_map[base]
    assert first_hour["mean"] == pytest.approx(5.0)
    assert first_hour["min"] == pytest.approx(0.0)
    assert first_hour["max"] == pytest.approx(10.0)
    assert first_hour["state"] == pytest.approx(10.0)

    third_hour = stat_map[base + timedelta(hours=2)]
    assert third_hour["mean"] == pytest.approx(20.0)
    assert third_hour["min"] == pytest.approx(20.0)
    assert third_hour["max"] == pytest.approx(20.0)
    assert third_hour["state"] == pytest.approx(20.0)

    fourth_hour = stat_map[base + timedelta(hours=3)]
    assert fourth_hour["mean"] == pytest.approx(20.0)
    assert fourth_hour["state"] == pytest.approx(20.0)


@pytest.mark.asyncio
async def test_step_statistics_propagate_forward() -> None:
    from homeassistant.core import HomeAssistant

    hass = HomeAssistant(asyncio.get_running_loop())
    coordinator = HASSEMSCoordinator(hass, client=AsyncMock(), entry=DummyConfigEntry())

    base = datetime(2024, 6, 1, 0, 30, tzinfo=timezone.utc)
    history = [
        {"measured_at": base.isoformat(), "value": 4},
        {"measured_at": (base + timedelta(hours=1)).isoformat(), "value": 7},
    ]

    points = coordinator._parse_measurement_points(history)
    window_start = base - timedelta(minutes=30)
    window_end = base + timedelta(hours=3)
    statistics = coordinator._calculate_hourly_statistics(
        points,
        "step",
        history_window=(window_start, window_end),
    )

    assert len(statistics) == 4
    stat_map = {item["start"]: item for item in statistics}

    first_hour_start = window_start.replace(minute=0, second=0, microsecond=0)
    first_hour = stat_map[first_hour_start]
    assert first_hour["mean"] == pytest.approx(4.0)
    assert first_hour["state"] == pytest.approx(4.0)

    final_hour_start = first_hour_start + timedelta(hours=3)
    final_hour = stat_map[final_hour_start]
    assert final_hour["mean"] == pytest.approx(7.0)
    assert final_hour["min"] == pytest.approx(7.0)
    assert final_hour["max"] == pytest.approx(7.0)
    assert final_hour["state"] == pytest.approx(7.0)
