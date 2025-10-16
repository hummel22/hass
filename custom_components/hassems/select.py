from __future__ import annotations

from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN
from .coordinator import HASSEMSCoordinator
from .entity import HASSEMSEntity


async def async_setup_entry(hass, entry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: HASSEMSCoordinator = data["coordinator"]

    def is_select(entity: dict[str, Any]) -> bool:
        return entity.get("type") == "input_select"

    entities: list[HASSEMSSelect] = []
    for slug, entity in (coordinator.data or {}).items():
        if is_select(entity):
            entities.append(HASSEMSSelect(coordinator, slug))
    async_add_entities(entities)

    @callback
    def _handle_added(slug: str) -> None:
        entity = coordinator.entity(slug)
        if entity and is_select(entity):
            async_add_entities([HASSEMSSelect(coordinator, slug)])

    entry.async_on_unload(
        async_dispatcher_connect(hass, coordinator.signal_add, _handle_added)
    )


class HASSEMSSelect(HASSEMSEntity, SelectEntity):
    @property
    def current_option(self) -> str | None:
        entity = self.entity
        if entity is None:
            return None
        value = entity.get("last_value")
        return str(value) if value is not None else None

    @property
    def options(self) -> list[str]:
        entity = self.entity
        if entity and entity.get("options"):
            return [str(option) for option in entity.get("options", [])]
        return []

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_entity_value(self._slug, option)

    @property
    def icon(self) -> str | None:
        entity = self.entity
        if entity:
            return entity.get("icon")
        return None
