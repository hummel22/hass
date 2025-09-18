"""Async client for interacting with a Home Assistant instance."""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

import httpx


DOMAIN_LIST_TEMPLATE = """
{% set domain_list = [] %}
{% for s in states %}
  {% if s.entity_id %}
    {% set domain = s.entity_id.split('.')[0] %}
    {% if domain and domain not in domain_list %}
      {% set domain_list = domain_list + [domain] %}
    {% endif %}
  {% endif %}
{% endfor %}
{{ domain_list | sort | to_json }}
"""


DOMAIN_SNAPSHOT_TEMPLATE = """
{% set target_domains = domains or [] %}
{% set entity_results = [] %}
{% set device_results = [] %}
{% set seen_devices = [] %}
{% for s in states %}
  {% if s.entity_id %}
    {% set domain = s.entity_id.split('.')[0] %}
    {% if domain in target_domains %}
      {% set entity = {
        'entity_id': s.entity_id,
        'name': s.name,
        'original_name': s.attributes.get('friendly_name'),
        'device_id': device_id(s.entity_id),
        'area_id': area_id(s.entity_id),
        'unique_id': state_attr(s.entity_id, 'unique_id'),
        'state': s.state,
        'attributes': s.attributes,
        'disabled_by': state_attr(s.entity_id, 'disabled_by')
      } %}
      {% set entity_results = entity_results + [entity] %}

      {% set dev_id = entity.device_id %}
      {% if dev_id %}
        {% set raw_identifiers = device_attr(dev_id, 'identifiers') or [] %}
        {% set identifiers = [] %}
        {% for identifier in raw_identifiers %}
          {% if identifier is iterable and identifier is not string %}
            {% set identifiers = identifiers + [identifier | list] %}
          {% else %}
            {% set identifiers = identifiers + [identifier] %}
          {% endif %}
        {% endfor %}

        {% if dev_id not in seen_devices %}
          {% set device_info = {
            'id': dev_id,
            'name': device_attr(dev_id, 'name'),
            'name_by_user': device_attr(dev_id, 'name_by_user'),
            'manufacturer': device_attr(dev_id, 'manufacturer'),
            'model': device_attr(dev_id, 'model'),
            'sw_version': device_attr(dev_id, 'sw_version'),
            'configuration_url': device_attr(dev_id, 'configuration_url'),
            'area_id': area_id(dev_id),
            'via_device_id': device_attr(dev_id, 'via_device_id'),
            'identifiers': identifiers
          } %}
          {% set device_results = device_results + [device_info] %}
          {% set seen_devices = seen_devices + [dev_id] %}
        {% endif %}
      {% endif %}
    {% endif %}
  {% endif %}
{% endfor %}
{{ {'entities': entity_results, 'devices': device_results} | to_json }}
"""


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

    async def render_template(
        self, template: str, variables: Optional[Dict[str, Any]] = None
    ) -> Any:
        payload: Dict[str, Any] = {"template": template}
        if variables:
            payload["variables"] = variables
        data = await self._request("POST", "/api/template", json=payload)
        if data is None:
            raise HomeAssistantError("Template response was empty")
        return data

    async def fetch_domains(self) -> List[str]:
        """Return a sorted list of available domains derived from entity states."""

        data = await self.render_template(DOMAIN_LIST_TEMPLATE)
        if not isinstance(data, list):
            raise HomeAssistantError("Unexpected response while fetching domains")
        return [domain for domain in data if isinstance(domain, str)]

    async def fetch_domain_snapshot(self, domains: Iterable[str]) -> Dict[str, Any]:
        """Return entity and device metadata for the provided domains."""

        domains = [domain for domain in domains if domain]
        if not domains:
            return {"entities": [], "devices": []}
        data = await self.render_template(
            DOMAIN_SNAPSHOT_TEMPLATE, {"domains": sorted(set(domains))}
        )
        if not isinstance(data, dict):
            raise HomeAssistantError("Unexpected response while fetching domain snapshot")
        entities = data.get("entities", [])
        devices = data.get("devices", [])
        if not isinstance(entities, list) or not isinstance(devices, list):
            raise HomeAssistantError("Unexpected template payload structure")
        return {"entities": entities, "devices": devices}


__all__ = [
    "HomeAssistantClient",
    "HomeAssistantError",
    "HomeAssistantSettings",
]
