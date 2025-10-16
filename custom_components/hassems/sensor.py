from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN, SIGNAL_ENTITY_ADDED
from .coordinator import HASSEMSCoordinator
from .entity import HASSEMSEntity

_EXCLUDED_TYPES = {"input_boolean", "input_number", "input_select", "input_text"}


def _is_sensor(entity: dict[str, Any]) -> bool:
    entity_kind = entity.get("type")
    return entity_kind not in _EXCLUDED_TYPES


async def async_setup_entry(hass, entry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: HASSEMSCoordinator = data["coordinator"]

    entities: list[HASSEMSSensor] = []
    for slug, entity in (coordinator.data or {}).items():
        if _is_sensor(entity):
            entities.append(HASSEMSSensor(coordinator, slug))
    async_add_entities(entities)

    @callback
    def _handle_added(slug: str) -> None:
        entity = coordinator.entity(slug)
        if entity and _is_sensor(entity):
            async_add_entities([HASSEMSSensor(coordinator, slug)])

    entry.async_on_unload(
        async_dispatcher_connect(hass, coordinator.signal_add, _handle_added)
    )


class HASSEMSSensor(HASSEMSEntity, SensorEntity):
    @property
    def native_value(self) -> Any:
        entity = self.entity
        if entity is None:
            return None
        value = entity.get("last_value")
        if entity.get("type") == "input_number":
            try:
                return float(value)
            except (TypeError, ValueError):
                return None
        return value

    @property
    def native_unit_of_measurement(self) -> str | None:
        entity = self.entity
        if entity:
            return entity.get("unit_of_measurement")
        return None

    @property
    def device_class(self) -> str | None:
        entity = self.entity
        if entity:
            return entity.get("device_class")
        return None

    @property
    def state_class(self) -> str | None:
        entity = self.entity
        if entity:
            return entity.get("state_class")
        return None

    @property
    def icon(self) -> str | None:
        entity = self.entity
        if entity:
            return entity.get("icon")
        return None
