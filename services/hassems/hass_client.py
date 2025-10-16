from __future__ import annotations

import os
from typing import Any, Dict, Optional

import httpx

from .models import EntityKind, ManagedEntity, coerce_entity_value


class HomeAssistantClient:
    """Thin wrapper around the Home Assistant REST API."""

    def __init__(self, base_url: str, token: str, *, timeout: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={"Authorization": f"Bearer {self._token}"},
            timeout=timeout,
        )

    @classmethod
    def from_env(cls) -> Optional["HomeAssistantClient"]:
        base_url = os.getenv("HASS_BASE_URL")
        token = os.getenv("HASS_ACCESS_TOKEN")
        if not base_url or not token:
            return None
        return cls(base_url, token)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get_state(self, entity_id: str) -> Dict[str, Any]:
        response = await self._client.get(f"/api/states/{entity_id}")
        response.raise_for_status()
        return response.json()

    async def set_entity_value(self, entity: ManagedEntity, value: Any) -> Dict[str, Any]:
        """Set the value of a Home Assistant input entity."""

        coerced_value = coerce_entity_value(entity.type, value, entity.options)
        domain = entity.type.value

        if entity.type == EntityKind.INPUT_BOOLEAN:
            service = "turn_on" if coerced_value else "turn_off"
            payload: Dict[str, Any] = {"entity_id": entity.entity_id}
        elif entity.type == EntityKind.INPUT_SELECT:
            service = "select_option"
            payload = {"entity_id": entity.entity_id, "option": coerced_value}
        else:  # input_text or input_number
            service = "set_value"
            payload = {"entity_id": entity.entity_id, "value": coerced_value}

        response = await self._client.post(f"/api/services/{domain}/{service}", json=payload)
        response.raise_for_status()
        return response.json()


__all__ = ["HomeAssistantClient"]
