"""Async client for interacting with a Home Assistant instance."""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx


class HomeAssistantError(RuntimeError):
    """Raised when communication with Home Assistant fails."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass
class HomeAssistantSettings:
    base_url: str
    access_token: str
    timeout: float = 10.0


class HomeAssistantClient:
    """Wrapper around the Home Assistant HTTP API."""

    def __init__(self, settings: HomeAssistantSettings) -> None:
        self._settings = settings
        self._client: Optional[httpx.AsyncClient] = None
        self._lock = asyncio.Lock()
        self._logger = logging.getLogger("hass_helper.http")

    @property
    def is_configured(self) -> bool:
        return bool(self._settings.base_url) and bool(self._settings.access_token)

    async def _get_client(self) -> httpx.AsyncClient:
        if not self.is_configured:
            raise HomeAssistantError(
                "Home Assistant base URL or access token is not configured."
            )
        async with self._lock:
            if self._client is None:
                headers = {
                    "Authorization": f"Bearer {self._settings.access_token}",
                    "Content-Type": "application/json",
                }
                self._client = httpx.AsyncClient(
                    base_url=self._settings.base_url.rstrip("/"),
                    headers=headers,
                    timeout=self._settings.timeout,
                )
        assert self._client is not None
        return self._client

    async def close(self) -> None:
        async with self._lock:
            if self._client is not None:
                await self._client.aclose()
                self._client = None

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        client = await self._get_client()
        start = time.perf_counter()
        try:
            response = await client.request(method, path, **kwargs)
            duration_ms = (time.perf_counter() - start) * 1000
            self._logger.debug(
                "home_assistant_http_call",
                extra={
                    "method": method,
                    "path": path,
                    "url": str(response.request.url),
                    "status_code": response.status_code,
                    "duration_ms": round(duration_ms, 3),
                },
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            response = exc.response
            request = response.request if response is not None else None
            self._logger.debug(
                "home_assistant_http_call",
                extra={
                    "method": method,
                    "path": path,
                    "url": str(request.url) if request else path,
                    "status_code": response.status_code if response else None,
                    "reason": response.reason_phrase if response else None,
                    "duration_ms": round(duration_ms, 3),
                    "error": True,
                },
            )
            raise HomeAssistantError(
                f"Home Assistant request failed: {exc.response.status_code} {exc.response.reason_phrase}",
                status_code=exc.response.status_code,
            ) from exc
        except httpx.HTTPError as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            request = getattr(exc, "request", None)
            url = str(request.url) if request else path
            self._logger.debug(
                "home_assistant_http_call",
                extra={
                    "method": method,
                    "path": path,
                    "url": url,
                    "duration_ms": round(duration_ms, 3),
                    "error": True,
                    "exception": exc.__class__.__name__,
                },
            )
            raise HomeAssistantError("Error communicating with Home Assistant") from exc
        if response.content:
            return response.json()
        return None

    async def fetch_integrations(self) -> List[Dict[str, Any]]:
        """Return the list of configured integration entries."""
        data = await self._request("GET", "/api/config/config_entries/entry")
        if not isinstance(data, list):
            raise HomeAssistantError("Unexpected response while fetching integrations")
        return data

    async def fetch_entity_registry(self) -> List[Dict[str, Any]]:
        try:
            data = await self._request("GET", "/api/config/entity_registry/list")
        except HomeAssistantError as exc:
            if exc.status_code not in {404, 405}:
                raise
            data = await self._request("POST", "/api/config/entity_registry/list", json={})
        if not isinstance(data, list):
            raise HomeAssistantError("Unexpected response while fetching entity registry")
        return data

    async def fetch_device_registry(self) -> List[Dict[str, Any]]:
        try:
            data = await self._request("GET", "/api/config/device_registry/list")
        except HomeAssistantError as exc:
            if exc.status_code not in {404, 405}:
                raise
            data = await self._request("POST", "/api/config/device_registry/list", json={})
        if not isinstance(data, list):
            raise HomeAssistantError("Unexpected response while fetching device registry")
        return data

    async def fetch_states(self) -> List[Dict[str, Any]]:
        data = await self._request("GET", "/api/states")
        if not isinstance(data, list):
            raise HomeAssistantError("Unexpected response while fetching states")
        return data


__all__ = [
    "HomeAssistantClient",
    "HomeAssistantError",
    "HomeAssistantSettings",
]
