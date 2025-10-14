from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN
from .coordinator import HASSEMSCoordinator
from .entity import HASSEMSEntity


async def async_setup_entry(hass, entry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: HASSEMSCoordinator = data["coordinator"]

    def is_boolean(helper: dict[str, Any]) -> bool:
        return helper.get("type") == "input_boolean"

    entities: list[HASSEMSSwitch] = []
    for slug, helper in (coordinator.data or {}).items():
        if is_boolean(helper):
            entities.append(HASSEMSSwitch(coordinator, slug))
    async_add_entities(entities)

    @callback
    def _handle_added(slug: str) -> None:
        helper = coordinator.helper(slug)
        if helper and is_boolean(helper):
            async_add_entities([HASSEMSSwitch(coordinator, slug)])

    entry.async_on_unload(
        async_dispatcher_connect(hass, coordinator.signal_add, _handle_added)
    )


class HASSEMSSwitch(HASSEMSEntity, SwitchEntity):
    @property
    def is_on(self) -> bool:
        helper = self.helper
        if helper is None:
            return False
        value = helper.get("last_value")
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in {"true", "on", "1"}
        return False

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_helper_value(self._slug, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_helper_value(self._slug, False)

    @property
    def icon(self) -> str | None:
        helper = self.helper
        if helper:
            return helper.get("icon")
        return None
