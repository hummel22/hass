from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import HASSEMSCoordinator
from .const import (
    ATTR_HISTORY,
    ATTR_HISTORY_CURSOR,
    ATTR_HISTORY_CURSOR_EVENTS,
    ATTR_LAST_MEASURED,
    ATTR_STATISTICS_MODE,
    DOMAIN,
)


_LOGGER = logging.getLogger(__name__)


class HASSEMSEntity(CoordinatorEntity[Dict[str, Dict[str, Any]]]):
    """Base class for HASSEMS entities."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator: HASSEMSCoordinator, slug: str) -> None:
        super().__init__(coordinator)
        self._slug = slug
        entity = self.entity
        unique_id = entity.get("unique_id") if entity else None
        self._attr_unique_id = unique_id or slug
        self._attr_name = entity.get("name") if entity else None

    @property
    def entity(self) -> Optional[Dict[str, Any]]:
        return self.coordinator.entity(self._slug)

    @property
    def available(self) -> bool:
        return self.entity is not None

    @property
    def device_info(self) -> Optional[DeviceInfo]:
        entity = self.entity
        if entity is None:
            return None
        identifiers = {(DOMAIN, entity.get("device_id") or entity["slug"])}
        for identifier in entity.get("device_identifiers") or []:
            identifiers.add((DOMAIN, identifier))
        return DeviceInfo(
            identifiers=identifiers,
            name=entity.get("device_name") or entity.get("name"),
            manufacturer=entity.get("device_manufacturer") or "HASSEMS",
            model=entity.get("device_model"),
            sw_version=entity.get("device_sw_version"),
        )

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        entity = self.entity
        attributes: Dict[str, Any] = {}
        if entity:
            measured_at = entity.get("last_measured_at")
            if measured_at:
                attributes[ATTR_LAST_MEASURED] = measured_at
            statistics_mode = entity.get(ATTR_STATISTICS_MODE)
            if statistics_mode:
                attributes[ATTR_STATISTICS_MODE] = statistics_mode
            history_cursor = entity.get("history_cursor")
            if history_cursor:
                attributes[ATTR_HISTORY_CURSOR] = history_cursor
            cursor_events = entity.get("history_cursor_events") or []
            if cursor_events:
                attributes[ATTR_HISTORY_CURSOR_EVENTS] = cursor_events
        history = self.coordinator.entity_history(self._slug)
        if history:
            attributes[ATTR_HISTORY] = history[-50:]
        return attributes

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.coordinator.register_entity(self._slug, self.entity_id)
        try:
            await self.coordinator.async_get_history(self._slug)
        except HomeAssistantError:
            _LOGGER.debug("Unable to pre-load history for %s", self._slug)
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                self.coordinator.signal_remove,
                self._async_handle_removed,
            )
        )

    async def async_will_remove_from_hass(self) -> None:
        self.coordinator.unregister_entity(self._slug)
        await super().async_will_remove_from_hass()

    async def _async_handle_removed(self, slug: str) -> None:
        if slug == self._slug:
            self.coordinator.unregister_entity(self._slug)
            await self.async_remove(force_remove=True)
