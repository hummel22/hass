from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx

from .models import InputHelper
from .storage import InputHelperStore, WebhookTarget

_LOGGER = logging.getLogger(__name__)


class WebhookNotifier:
    """Dispatches helper events to subscribed Home Assistant webhooks."""

    def __init__(self, store: InputHelperStore) -> None:
        self._store = store

    async def helper_created(self, helper: InputHelper) -> None:
        await self._broadcast("helper_created", helper)

    async def helper_updated(self, helper: InputHelper) -> None:
        await self._broadcast("helper_updated", helper)

    async def helper_deleted(self, helper: InputHelper) -> None:
        await self._broadcast("helper_deleted", helper)

    async def helper_value(
        self,
        helper: InputHelper,
        *,
        value: Any,
        measured_at: datetime,
    ) -> None:
        await self._broadcast(
            "helper_value",
            helper,
            data={
                "value": value,
                "measured_at": measured_at.astimezone(timezone.utc).isoformat(),
            },
        )

    async def _broadcast(
        self,
        event: str,
        helper: InputHelper,
        data: Optional[Dict[str, Any]] = None,
    ) -> None:
        targets = self._store.list_webhook_targets()
        if not targets:
            return

        payload = {
            "event": event,
            "helper": helper.model_dump(mode="json"),
            "data": data or {},
            "subscription_ids": [target.id for target in targets],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            coroutines = [
                self._post_payload(client, target, payload, event, helper.slug)
                for target in targets
            ]
            results = await asyncio.gather(*coroutines, return_exceptions=True)
            for index, target in enumerate(targets):
                result = results[index]
                if isinstance(result, Exception):
                    _LOGGER.warning(
                        "Failed to deliver webhook event '%s' to %s: %s",
                        event,
                        target.webhook_url,
                        result,
                    )

    async def _post_payload(
        self,
        client: httpx.AsyncClient,
        target: WebhookTarget,
        payload: Dict[str, Any],
        event: str,
        slug: str,
    ) -> None:
        headers = {
            "Content-Type": "application/json",
            "X-HASSEMS-Event": event,
            "X-HASSEMS-Helper": slug,
            "X-HASSEMS-Token": target.token,
            "X-HASSEMS-Subscription": str(target.id),
        }
        if target.secret:
            headers["Authorization"] = f"Bearer {target.secret}"
        if target.description:
            headers["X-HASSEMS-Description"] = target.description
        if target.metadata:
            metadata_query = {key: str(value) for key, value in target.metadata.items()}
            headers["X-HASSEMS-Metadata"] = httpx.QueryParams(metadata_query).to_str()

        await client.post(target.webhook_url, json=payload, headers=headers, follow_redirects=False)
