from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN, SIGNAL_HELPER_ADDED
from .coordinator import HASSEMSCoordinator
from .entity import HASSEMSEntity

_EXCLUDED_TYPES = {"input_boolean", "input_number", "input_select", "input_text"}


def _is_sensor(helper: dict[str, Any]) -> bool:
    helper_type = helper.get("type")
    return helper_type not in _EXCLUDED_TYPES


async def async_setup_entry(hass, entry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: HASSEMSCoordinator = data["coordinator"]

    entities: list[HASSEMSSensor] = []
    for slug, helper in (coordinator.data or {}).items():
        if _is_sensor(helper):
            entities.append(HASSEMSSensor(coordinator, slug))
    async_add_entities(entities)

    @callback
    def _handle_added(slug: str) -> None:
        helper = coordinator.helper(slug)
        if helper and _is_sensor(helper):
            async_add_entities([HASSEMSSensor(coordinator, slug)])

    entry.async_on_unload(
        async_dispatcher_connect(hass, coordinator.signal_add, _handle_added)
    )


class HASSEMSSensor(HASSEMSEntity, SensorEntity):
    @property
    def native_value(self) -> Any:
        helper = self.helper
        if helper is None:
            return None
        value = helper.get("last_value")
        if helper.get("type") == "input_number":
            try:
                return float(value)
            except (TypeError, ValueError):
                return None
        return value

    @property
    def native_unit_of_measurement(self) -> str | None:
        helper = self.helper
        if helper:
            return helper.get("unit_of_measurement")
        return None

    @property
    def device_class(self) -> str | None:
        helper = self.helper
        if helper:
            return helper.get("device_class")
        return None

    @property
    def state_class(self) -> str | None:
        helper = self.helper
        if helper:
            return helper.get("state_class")
        return None

    @property
    def icon(self) -> str | None:
        helper = self.helper
        if helper:
            return helper.get("icon")
        return None
