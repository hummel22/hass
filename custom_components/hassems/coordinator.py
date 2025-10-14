from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Set

from aiohttp import web
from homeassistant import config_entries
from homeassistant.components import recorder
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    ATTR_ENTITY_ID,
    ATTR_UNIT_OF_MEASUREMENT,
    EVENT_STATE_CHANGED,
)
from homeassistant.core import Context, Event, EventOrigin, HomeAssistant, State
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import HASSEMSAuthError, HASSEMSError, HASSEMSClient
from .const import (
    ATTR_HISTORY,
    ATTR_LAST_MEASURED,
    ATTR_STATE_CLASS,
    CONF_INCLUDED_HELPERS,
    CONF_IGNORED_HELPERS,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    EVENT_HELPER_CREATED,
    EVENT_HELPER_DELETED,
    EVENT_HELPER_UPDATED,
    EVENT_HELPER_VALUE,
    SIGNAL_HELPER_ADDED,
    SIGNAL_HELPER_REMOVED,
    SIGNAL_HELPER_UPDATED,
)

_LOGGER = logging.getLogger(__name__)


class HASSEMSCoordinator(DataUpdateCoordinator[Dict[str, Dict[str, Any]]]):
    """Coordinator responsible for synchronising data with HASSEMS."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: HASSEMSClient,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="HASSEMS",
            update_interval=DEFAULT_POLL_INTERVAL,
        )
        self.client = client
        self.entry = entry
        self._helpers: Dict[str, Dict[str, Any]] = {}
        self._history: Dict[str, List[Dict[str, Any]]] = {}
        self._recorded_measurements: Dict[str, OrderedDict[str, None]] = {}
        self._pending_discoveries: Set[str] = set()
        self._included: Set[str] = set(entry.options.get(CONF_INCLUDED_HELPERS, []))
        self._ignored: Set[str] = set(entry.options.get(CONF_IGNORED_HELPERS, []))
        self._subscription_id: Optional[int] = entry.data.get("subscription_id")

        self.signal_add = SIGNAL_HELPER_ADDED.format(entry_id=entry.entry_id)
        self.signal_remove = SIGNAL_HELPER_REMOVED.format(entry_id=entry.entry_id)
        self.signal_update = SIGNAL_HELPER_UPDATED.format(entry_id=entry.entry_id)

    @property
    def subscription_id(self) -> Optional[int]:
        return self._subscription_id

    def set_subscription(self, subscription: Dict[str, Any]) -> None:
        sub_id = subscription.get("id")
        if sub_id is not None:
            try:
                self._subscription_id = int(sub_id)
            except (TypeError, ValueError):
                _LOGGER.debug("Unexpected subscription id format: %s", sub_id)

    def update_filters(
        self,
        *,
        included: Optional[Set[str]] = None,
        ignored: Optional[Set[str]] = None,
    ) -> None:
        if included is not None:
            self._included = set(included)
        if ignored is not None:
            self._ignored = set(ignored)
        self._pending_discoveries -= self._included
        self._pending_discoveries -= self._ignored

    async def async_update_options(self, entry: ConfigEntry) -> None:
        self.entry = entry
        self.update_filters(
            included=set(entry.options.get(CONF_INCLUDED_HELPERS, [])),
            ignored=set(entry.options.get(CONF_IGNORED_HELPERS, [])),
        )
        self.reapply_filters()
        await self.async_request_refresh()

    def reapply_filters(self) -> None:
        allowed_slugs = self._select_allowed_slugs(self._helpers)
        allowed_set = set(allowed_slugs)
        current = dict(self.data or {})
        updated = {
            slug: self._helpers[slug]
            for slug in allowed_slugs
            if slug in self._helpers
        }
        removed = [slug for slug in current if slug not in allowed_set]
        added = [slug for slug in allowed_slugs if slug not in current]

        self._history = {slug: self._history.get(slug, []) for slug in allowed_slugs}
        self._recorded_measurements = {
            slug: self._recorded_measurements.get(slug, OrderedDict())
            for slug in allowed_slugs
        }

        if current != updated:
            self.async_set_updated_data(updated)

        for slug in removed:
            async_dispatcher_send(self.hass, self.signal_remove, slug)
        for slug in added:
            async_dispatcher_send(self.hass, self.signal_add, slug)

    async def _async_update_data(self) -> Dict[str, Dict[str, Any]]:
        try:
            helpers = await self.client.async_list_helpers()
        except HASSEMSAuthError as exc:
            raise ConfigEntryAuthFailed(str(exc)) from exc
        except HASSEMSError as exc:
            raise UpdateFailed(str(exc)) from exc

        mapping: Dict[str, Dict[str, Any]] = {helper["slug"]: helper for helper in helpers if helper.get("slug")}
        self._helpers = mapping

        allowed_slugs = self._select_allowed_slugs(mapping)
        current_slugs = set(self.data or {})
        added = [slug for slug in allowed_slugs if slug not in current_slugs]
        removed = [slug for slug in current_slugs if slug not in allowed_slugs]

        await self._fetch_history_for_new(added)

        data = {slug: mapping[slug] for slug in allowed_slugs}
        self._history = {slug: self._history.get(slug, []) for slug in allowed_slugs}
        self._recorded_measurements = {
            slug: self._recorded_measurements.get(slug, OrderedDict())
            for slug in allowed_slugs
        }

        if added:
            for slug in added:
                async_dispatcher_send(self.hass, self.signal_add, slug)
        if removed:
            for slug in removed:
                async_dispatcher_send(self.hass, self.signal_remove, slug)
        return data

    async def _fetch_history_for_new(self, slugs: List[str]) -> None:
        if not slugs:
            return
        tasks = [self.client.async_get_history(slug) for slug in slugs]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for slug, result in zip(slugs, results):
            if isinstance(result, HASSEMSAuthError):
                raise ConfigEntryAuthFailed(str(result)) from result
            if isinstance(result, HASSEMSError):
                _LOGGER.warning("Unable to load history for %s: %s", slug, result)
                self._history[slug] = []
            elif isinstance(result, Exception):
                _LOGGER.warning("Unexpected error loading history for %s: %s", slug, result)
                self._history[slug] = []
            else:
                self._history[slug] = list(result)
            if self._history.get(slug):
                await self._async_store_measurements(slug, self._history[slug])

    def _select_allowed_slugs(self, mapping: Dict[str, Dict[str, Any]]) -> List[str]:
        available = set(mapping.keys())
        if self._included:
            allowed = self._included & available
        else:
            allowed = available - self._ignored
        return [
            slug
            for slug, _ in sorted(
                ((slug, mapping[slug]) for slug in allowed),
                key=lambda item: (item[1].get("name") or item[0]),
            )
        ]

    async def async_get_history(self, slug: str) -> List[Dict[str, Any]]:
        if slug not in self._history:
            try:
                history = await self.client.async_get_history(slug)
            except HASSEMSAuthError as exc:
                raise ConfigEntryAuthFailed(str(exc)) from exc
            except HASSEMSError as exc:
                raise HomeAssistantError(str(exc)) from exc
            self._history[slug] = list(history)
            if self._history[slug]:
                await self._async_store_measurements(slug, self._history[slug])
        return list(self._history.get(slug, []))

    async def async_set_helper_value(self, slug: str, value: Any) -> None:
        try:
            await self.client.async_set_value(slug, value)
        except HASSEMSAuthError as exc:
            raise ConfigEntryAuthFailed(str(exc)) from exc
        except HASSEMSError as exc:
            raise HomeAssistantError(str(exc)) from exc

    async def async_handle_webhook(self, hass: HomeAssistant, webhook_id: str, request) -> web.Response:
        token_header = request.headers.get("X-HASSEMS-Token")
        expected = self.entry.data.get("token")
        if expected and token_header != expected:
            return web.Response(status=401)
        try:
            payload = await request.json()
        except Exception:  # noqa: BLE001
            return web.Response(status=400)
        event = request.headers.get("X-HASSEMS-Event") or payload.get("event")
        if not event:
            return web.Response(status=400)
        await self._async_process_event(event, payload)
        return web.Response(status=200)

    async def _async_process_event(self, event: str, payload: Dict[str, Any]) -> None:
        helper = payload.get("helper") or {}
        slug = helper.get("slug")
        if not slug:
            return

        if event == EVENT_HELPER_DELETED:
            self._helpers.pop(slug, None)
            if self.data and slug in self.data:
                new_data = dict(self.data)
                new_data.pop(slug, None)
                self._history.pop(slug, None)
                self._recorded_measurements.pop(slug, None)
                self.async_set_updated_data(new_data)
                async_dispatcher_send(self.hass, self.signal_remove, slug)
            return

        self._helpers[slug] = helper
        self._pending_discoveries.discard(slug)

        if event == EVENT_HELPER_VALUE:
            measurement = (payload.get("data") or {}).get("measured_at")
            value = (payload.get("data") or {}).get("value")
            history = self._history.setdefault(slug, [])
            history.append({
                "value": value,
                "measured_at": measurement,
            })
            if len(history) > 50:
                del history[:-50]
            if measurement:
                await self._async_store_measurements(slug, [history[-1]])

        allowed_slugs = set(self._select_allowed_slugs(self._helpers))
        if slug not in allowed_slugs:
            await self._async_prompt_discovery(helper)
            return

        existed = slug in (self.data or {})
        new_data = dict(self.data or {})
        new_data[slug] = helper
        self.async_set_updated_data(new_data)
        if existed:
            async_dispatcher_send(self.hass, self.signal_update, slug)
        else:
            async_dispatcher_send(self.hass, self.signal_add, slug)

    async def _async_prompt_discovery(self, helper: Dict[str, Any]) -> None:
        slug = helper.get("slug")
        if not slug or slug in self._pending_discoveries or slug in self._ignored:
            return
        self._pending_discoveries.add(slug)
        self.hass.async_create_task(
            self.hass.config_entries.flow.async_init(
                DOMAIN,
                context={
                    "source": config_entries.SOURCE_INTEGRATION_DISCOVERY,
                    "entry_id": self.entry.entry_id,
                },
                data={"helper": helper},
            )
        )

    def helper(self, slug: str) -> Optional[Dict[str, Any]]:
        if self.data:
            return self.data.get(slug)
        return None

    def helper_history(self, slug: str) -> List[Dict[str, Any]]:
        return list(self._history.get(slug, []))

    async def _async_store_measurements(
        self, slug: str, measurements: List[Dict[str, Any]]
    ) -> None:
        helper = self._helpers.get(slug)
        if not helper:
            return
        entity_id = helper.get("entity_id")
        if not entity_id:
            return
        try:
            instance = recorder.get_instance(self.hass)
        except KeyError:
            return
        if not instance.is_running:
            return
        try:
            if not recorder.is_entity_recorded(self.hass, entity_id):
                return
        except KeyError:
            return

        recorded = self._recorded_measurements.setdefault(slug, OrderedDict())
        state_obj = self.hass.states.get(entity_id)
        if state_obj is not None:
            base_attributes = {
                key: value
                for key, value in state_obj.attributes.items()
                if key != ATTR_HISTORY
            }
        else:
            base_attributes = {}
            if (unit := helper.get("unit_of_measurement")) is not None:
                base_attributes[ATTR_UNIT_OF_MEASUREMENT] = unit
            if (device_class := helper.get("device_class")) is not None:
                base_attributes[ATTR_DEVICE_CLASS] = device_class
            if (state_class := helper.get("state_class")) is not None:
                base_attributes[ATTR_STATE_CLASS] = state_class
            if (icon := helper.get("icon")) is not None:
                base_attributes["icon"] = icon

        events: List[Event] = []
        previous_state: State | None = None

        for item in sorted(
            measurements, key=lambda entry: entry.get("measured_at") or ""
        ):
            measured_at = item.get("measured_at")
            if not measured_at or measured_at in recorded:
                continue
            dt_value = dt_util.parse_datetime(measured_at)
            if dt_value is None:
                continue
            dt_value = dt_util.as_utc(dt_value)
            state_value = item.get("value")
            state_str = "" if state_value is None else str(state_value)

            attributes = dict(base_attributes)
            attributes.pop(ATTR_HISTORY, None)
            attributes[ATTR_LAST_MEASURED] = measured_at

            context = Context()
            new_state = State(
                entity_id,
                state_str,
                attributes,
                last_changed=dt_value,
                last_updated=dt_value,
                context=context,
            )
            event = Event(
                EVENT_STATE_CHANGED,
                {
                    ATTR_ENTITY_ID: entity_id,
                    "old_state": previous_state,
                    "new_state": new_state,
                },
                context=context,
                origin=EventOrigin.remote,
            )
            event.time_fired = dt_value
            events.append(event)
            recorded[measured_at] = None
            while len(recorded) > 200:
                recorded.popitem(last=False)
            previous_state = new_state

        if not events:
            return

        for event in events:
            instance._queue.put_nowait(event)
