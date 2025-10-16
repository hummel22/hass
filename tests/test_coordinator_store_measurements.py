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
    coordinator._helpers["test"] = {
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
    coordinator._helpers["test"] = {
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
    coordinator._helpers["test"] = {
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
