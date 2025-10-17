from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import pytest
from unittest.mock import AsyncMock

from custom_components.hassems.coordinator import HASSEMSCoordinator


class DummyConfigEntry:
    def __init__(self) -> None:
        self.data: Dict[str, Any] = {}
        self.options: Dict[str, Any] = {}
        self.entry_id = "entry"


@pytest.mark.asyncio
async def test_calculate_hourly_statistics_linear() -> None:
    from homeassistant.core import HomeAssistant

    hass = HomeAssistant(asyncio.get_running_loop())
    coordinator = HASSEMSCoordinator(hass, client=AsyncMock(), entry=DummyConfigEntry())

    start = datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc)
    points = [
        (start, 0.0),
        (start + timedelta(minutes=30), 5.0),
        (start + timedelta(hours=1), 10.0),
    ]

    stats = coordinator._calculate_hourly_statistics(points, "linear")

    assert len(stats) == 1
    stat = stats[0]
    assert stat["start"] == start
    assert stat["mean"] == pytest.approx(5.0)
    assert stat["min"] == pytest.approx(0.0)
    assert stat["max"] == pytest.approx(10.0)
    assert stat["state"] == pytest.approx(10.0)


@pytest.mark.asyncio
async def test_calculate_hourly_statistics_step() -> None:
    from homeassistant.core import HomeAssistant

    hass = HomeAssistant(asyncio.get_running_loop())
    coordinator = HASSEMSCoordinator(hass, client=AsyncMock(), entry=DummyConfigEntry())

    start = datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc)
    points = [
        (start, 2.0),
        (start + timedelta(minutes=30), 4.0),
        (start + timedelta(hours=1), 6.0),
    ]

    stats = coordinator._calculate_hourly_statistics(points, "step")

    assert len(stats) == 1
    stat = stats[0]
    assert stat["start"] == start
    assert stat["mean"] == pytest.approx(3.0)
    assert stat["min"] == pytest.approx(2.0)
    assert stat["max"] == pytest.approx(6.0)
    assert stat["state"] == pytest.approx(6.0)


@pytest.mark.asyncio
async def test_calculate_hourly_statistics_point() -> None:
    from homeassistant.core import HomeAssistant

    hass = HomeAssistant(asyncio.get_running_loop())
    coordinator = HASSEMSCoordinator(hass, client=AsyncMock(), entry=DummyConfigEntry())

    hour_start = datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc)
    points = [
        (hour_start + timedelta(minutes=5), 1.0),
        (hour_start + timedelta(minutes=25), 3.0),
        (hour_start + timedelta(minutes=55), 5.0),
        (hour_start + timedelta(hours=1, minutes=10), 7.0),
    ]

    stats = coordinator._calculate_hourly_statistics(points, "point")

    assert len(stats) == 2

    first_hour, second_hour = stats

    assert first_hour["start"] == hour_start
    assert first_hour["mean"] == pytest.approx(3.0)
    assert first_hour["min"] == pytest.approx(1.0)
    assert first_hour["max"] == pytest.approx(5.0)
    assert first_hour["state"] == pytest.approx(5.0)

    assert second_hour["start"] == hour_start + timedelta(hours=1)
    assert second_hour["mean"] == pytest.approx(7.0)
    assert second_hour["min"] == pytest.approx(7.0)
    assert second_hour["max"] == pytest.approx(7.0)
    assert second_hour["state"] == pytest.approx(7.0)
