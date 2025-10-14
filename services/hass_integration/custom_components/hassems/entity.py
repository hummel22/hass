from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import HASSEMSCoordinator
from .const import ATTR_HISTORY, ATTR_LAST_MEASURED, DOMAIN


_LOGGER = logging.getLogger(__name__)


class HASSEMSEntity(CoordinatorEntity[Dict[str, Dict[str, Any]]]):
    """Base class for HASSEMS entities."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator: HASSEMSCoordinator, slug: str) -> None:
        super().__init__(coordinator)
        self._slug = slug
        helper = self.helper
        unique_id = helper.get("unique_id") if helper else None
        self._attr_unique_id = unique_id or slug
        self._attr_name = helper.get("name") if helper else None

    @property
    def helper(self) -> Optional[Dict[str, Any]]:
        return self.coordinator.helper(self._slug)

    @property
    def available(self) -> bool:
        return self.helper is not None

    @property
    def device_info(self) -> Optional[DeviceInfo]:
        helper = self.helper
        if helper is None:
            return None
        identifiers = {(DOMAIN, helper.get("device_id") or helper["slug"])}
        for identifier in helper.get("device_identifiers") or []:
            identifiers.add((DOMAIN, identifier))
        return DeviceInfo(
            identifiers=identifiers,
            name=helper.get("device_name") or helper.get("name"),
            manufacturer=helper.get("device_manufacturer") or "HASSEMS",
            model=helper.get("device_model"),
            sw_version=helper.get("device_sw_version"),
        )

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        helper = self.helper
        attributes: Dict[str, Any] = {}
        if helper:
            measured_at = helper.get("last_measured_at")
            if measured_at:
                attributes[ATTR_LAST_MEASURED] = measured_at
        history = self.coordinator.helper_history(self._slug)
        if history:
            attributes[ATTR_HISTORY] = history[-50:]
        return attributes

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
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

    async def _async_handle_removed(self, slug: str) -> None:
        if slug == self._slug:
            await self.async_remove(force_remove=True)
