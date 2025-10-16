from __future__ import annotations

from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import callback
from homeassistant.entities.dispatcher import async_dispatcher_connect

from .const import DOMAIN
from .coordinator import HASSEMSCoordinator
from .entity import HASSEMSEntity


async def async_setup_entry(hass, entry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: HASSEMSCoordinator = data["coordinator"]

    def is_number(entity: dict[str, Any]) -> bool:
        return entity.get("type") == "input_number"

    entities: list[HASSEMSNumber] = []
    for slug, entity in (coordinator.data or {}).items():
        if is_number(entity):
            entities.append(HASSEMSNumber(coordinator, slug))
    async_add_entities(entities)

    @callback
    def _handle_added(slug: str) -> None:
        entity = coordinator.entity(slug)
        if entity and is_number(entity):
            async_add_entities([HASSEMSNumber(coordinator, slug)])

    entry.async_on_unload(
        async_dispatcher_connect(hass, coordinator.signal_add, _handle_added)
    )


class HASSEMSNumber(HASSEMSEntity, NumberEntity):
    _attr_mode = NumberMode.BOX

    @property
    def native_value(self) -> float | None:
        entity = self.entity
        if entity is None:
            return None
        value = entity.get("last_value")
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_entity_value(self._slug, value)

    @property
    def native_unit_of_measurement(self) -> str | None:
        entity = self.entity
        if entity:
            return entity.get("unit_of_measurement")
        return None

    @property
    def icon(self) -> str | None:
        entity = self.entity
        if entity:
            return entity.get("icon")
        return None
