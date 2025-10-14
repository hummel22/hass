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

    def is_select(helper: dict[str, Any]) -> bool:
        return helper.get("type") == "input_select"

    entities: list[HASSEMSSelect] = []
    for slug, helper in (coordinator.data or {}).items():
        if is_select(helper):
            entities.append(HASSEMSSelect(coordinator, slug))
    async_add_entities(entities)

    @callback
    def _handle_added(slug: str) -> None:
        helper = coordinator.helper(slug)
        if helper and is_select(helper):
            async_add_entities([HASSEMSSelect(coordinator, slug)])

    entry.async_on_unload(
        async_dispatcher_connect(hass, coordinator.signal_add, _handle_added)
    )


class HASSEMSSelect(HASSEMSEntity, SelectEntity):
    @property
    def current_option(self) -> str | None:
        helper = self.helper
        if helper is None:
            return None
        value = helper.get("last_value")
        return str(value) if value is not None else None

    @property
    def options(self) -> list[str]:
        helper = self.helper
        if helper and helper.get("options"):
            return [str(option) for option in helper.get("options", [])]
        return []

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_helper_value(self._slug, option)

    @property
    def icon(self) -> str | None:
        helper = self.helper
        if helper:
            return helper.get("icon")
        return None
