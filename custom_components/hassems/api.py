from __future__ import annotations

from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

from aiohttp import ClientError, ClientResponse


class HASSEMSAuthError(Exception):
    """Raised when the HASSEMS API reports an authentication error."""


class HASSEMSError(Exception):
    """Raised when an unexpected response is returned from HASSEMS."""


class HASSEMSClient:
    """Simple HTTP client for the HASSEMS API."""

    def __init__(self, session, base_url: str, token: str) -> None:
        self._session = session
        self._base_url = base_url.rstrip("/") + "/"
        self._token = token

    @property
    def base_url(self) -> str:
        return self._base_url

    def _headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        if self._token:
            headers["X-HASSEMS-Token"] = self._token
        return headers

    def _url(self, path: str) -> str:
        path = path.lstrip("/")
        return urljoin(self._base_url, f"api/{path}")

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = self._url(path)
        headers = kwargs.pop("headers", {}) or {}
        headers.update(self._headers())
        try:
            async with self._session.request(method, url, headers=headers, **kwargs) as response:
                return await self._handle_response(response)
        except ClientError as err:
            raise HASSEMSError(f"Error communicating with HASSEMS at {url}: {err}") from err

    async def _handle_response(self, response: ClientResponse) -> Any:
        if response.status == 204:
            return None
        if response.status == 401:
            raise HASSEMSAuthError("Invalid API token")
        if response.status >= 400:
            text = await response.text()
            raise HASSEMSError(f"HASSEMS request failed ({response.status}): {text}")
        if response.content_type == "application/json":
            return await response.json()
        return await response.text()

    async def async_health(self) -> Dict[str, Any]:
        return await self._request("GET", "/health")

    async def async_list_entities(self) -> List[Dict[str, Any]]:
        data = await self._request("GET", "/integrations/home-assistant/entities")
        return data if isinstance(data, list) else []

    async def async_get_entity(self, slug: str) -> Dict[str, Any]:
        return await self._request("GET", f"/integrations/home-assistant/entities/{slug}")

    async def async_get_history(self, slug: str, *, full: bool = False) -> List[Dict[str, Any]]:
        path = f"/integrations/home-assistant/entities/{slug}/history"
        if full:
            path += "?full=1"
        data = await self._request("GET", path)
        return data if isinstance(data, list) else []

    async def async_set_value(self, slug: str, value: Any) -> Dict[str, Any]:
        payload = {"value": value}
        return await self._request(
            "POST",
            f"/integrations/home-assistant/entities/{slug}/set",
            json=payload,
        )

    async def async_register_webhook(
        self,
        webhook_url: str,
        *,
        description: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"webhook_url": webhook_url}
        if description:
            payload["description"] = description
        if metadata:
            payload["metadata"] = metadata
        return await self._request(
            "POST",
            "/integrations/home-assistant/webhooks",
            json=payload,
        )

    async def async_list_webhooks(self) -> List[Dict[str, Any]]:
        data = await self._request("GET", "/integrations/home-assistant/webhooks")
        return data if isinstance(data, list) else []

    async def async_delete_webhook(self, subscription_id: int) -> None:
        await self._request(
            "DELETE",
            f"/integrations/home-assistant/webhooks/{subscription_id}",
        )

    async def async_upsert_connection(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        result = await self._request(
            "POST",
            "/integrations/home-assistant/connections",
            json=payload,
        )
        if isinstance(result, dict):
            return result
        raise HASSEMSError("Unexpected response when saving integration connection")

    async def async_delete_connection(self, entry_id: str) -> None:
        await self._request(
            "DELETE",
            f"/integrations/home-assistant/connections/{entry_id}",
        )
