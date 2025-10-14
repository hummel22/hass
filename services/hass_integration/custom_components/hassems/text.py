from __future__ import annotations

from typing import Any

from homeassistant.components.text import TextEntity
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN
from .coordinator import HASSEMSCoordinator
from .entity import HASSEMSEntity


async def async_setup_entry(hass, entry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: HASSEMSCoordinator = data["coordinator"]

    def is_text(helper: dict[str, Any]) -> bool:
        return helper.get("type") == "input_text"

    entities: list[HASSEMSText] = []
    for slug, helper in (coordinator.data or {}).items():
        if is_text(helper):
            entities.append(HASSEMSText(coordinator, slug))
    async_add_entities(entities)

    @callback
    def _handle_added(slug: str) -> None:
        helper = coordinator.helper(slug)
        if helper and is_text(helper):
            async_add_entities([HASSEMSText(coordinator, slug)])

    entry.async_on_unload(
        async_dispatcher_connect(hass, coordinator.signal_add, _handle_added)
    )


class HASSEMSText(HASSEMSEntity, TextEntity):
    @property
    def native_value(self) -> str | None:
        helper = self.helper
        if helper is None:
            return None
        value = helper.get("last_value")
        return str(value) if value is not None else None

    async def async_set_value(self, value: str) -> None:
        await self.coordinator.async_set_helper_value(self._slug, value)

    @property
    def icon(self) -> str | None:
        helper = self.helper
        if helper:
            return helper.get("icon")
        return None
