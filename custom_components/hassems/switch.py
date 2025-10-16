from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import callback
from homeassistant.entities.dispatcher import async_dispatcher_connect

from .const import DOMAIN
from .coordinator import HASSEMSCoordinator
from .entity import HASSEMSEntity


async def async_setup_entry(hass, entry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: HASSEMSCoordinator = data["coordinator"]

    def is_boolean(entity: dict[str, Any]) -> bool:
        return entity.get("type") == "input_boolean"

    entities: list[HASSEMSSwitch] = []
    for slug, entity in (coordinator.data or {}).items():
        if is_boolean(entity):
            entities.append(HASSEMSSwitch(coordinator, slug))
    async_add_entities(entities)

    @callback
    def _handle_added(slug: str) -> None:
        entity = coordinator.entity(slug)
        if entity and is_boolean(entity):
            async_add_entities([HASSEMSSwitch(coordinator, slug)])

    entry.async_on_unload(
        async_dispatcher_connect(hass, coordinator.signal_add, _handle_added)
    )


class HASSEMSSwitch(HASSEMSEntity, SwitchEntity):
    @property
    def is_on(self) -> bool:
        entity = self.entity
        if entity is None:
            return False
        value = entity.get("last_value")
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in {"true", "on", "1"}
        return False

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_entity_value(self._slug, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_entity_value(self._slug, False)

    @property
    def icon(self) -> str | None:
        entity = self.entity
        if entity:
            return entity.get("icon")
        return None
