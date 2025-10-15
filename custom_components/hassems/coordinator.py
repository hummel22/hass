from __future__ import annotations

import asyncio
import logging
import math
from collections import OrderedDict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

from aiohttp import web
from homeassistant import config_entries
from homeassistant.components import recorder
from homeassistant.components.recorder.statistics import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
    async_add_external_statistics,
    clear_statistics,
)
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
    DATA_HISTORY_CURSORS,
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

MAX_HISTORY_POINTS = 10000


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
        stored_cursors = entry.data.get(DATA_HISTORY_CURSORS, {})
        if isinstance(stored_cursors, dict):
            self._history_cursors = {
                str(slug): str(cursor)
                for slug, cursor in stored_cursors.items()
                if isinstance(slug, str) and cursor is not None
            }
        else:
            self._history_cursors = {}
        self._history_cursors_dirty = False
        self._entity_ids: Dict[str, str] = {}
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

        for slug in allowed_slugs:
            helper_data = mapping[slug]
            await self._async_process_history_cursor(slug, helper_data)

        removed_cursor_slugs = [
            slug for slug in list(self._history_cursors) if slug not in mapping
        ]
        for slug in removed_cursor_slugs:
            self._history_cursors.pop(slug, None)
            self._mark_history_cursors_dirty()
        self._save_history_cursors_if_needed()

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
        tasks = [self.client.async_get_history(slug, full=True) for slug in slugs]
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
                normalized = self._normalize_history_records(result)
                self._history[slug] = normalized
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
                history = await self.client.async_get_history(slug, full=True)
            except HASSEMSAuthError as exc:
                raise ConfigEntryAuthFailed(str(exc)) from exc
            except HASSEMSError as exc:
                raise HomeAssistantError(str(exc)) from exc
            normalized = self._normalize_history_records(history)
            self._history[slug] = normalized
            if normalized:
                await self._async_store_measurements(slug, normalized)
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
                self._entity_ids.pop(slug, None)
                if slug in self._history_cursors:
                    self._history_cursors.pop(slug, None)
                    self._mark_history_cursors_dirty()
                self.async_set_updated_data(new_data)
                async_dispatcher_send(self.hass, self.signal_remove, slug)
            self._save_history_cursors_if_needed()
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
            if len(history) > MAX_HISTORY_POINTS:
                del history[:-MAX_HISTORY_POINTS]
            if measurement:
                await self._async_store_measurements(slug, [history[-1]])

        await self._async_process_history_cursor(slug, helper)
        self._save_history_cursors_if_needed()

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

    def register_entity(self, slug: str, entity_id: str | None) -> None:
        if not entity_id:
            return
        self._entity_ids[slug] = entity_id

    def unregister_entity(self, slug: str) -> None:
        self._entity_ids.pop(slug, None)

    def _mark_history_cursors_dirty(self) -> None:
        self._history_cursors_dirty = True

    def _save_history_cursors_if_needed(self) -> None:
        if not self._history_cursors_dirty:
            return
        existing = {}
        stored = self.entry.data.get(DATA_HISTORY_CURSORS)
        if isinstance(stored, dict):
            existing = {
                str(slug): str(cursor)
                for slug, cursor in stored.items()
                if isinstance(slug, str) and cursor is not None
            }
        if existing == self._history_cursors:
            self._history_cursors_dirty = False
            return
        new_data = dict(self.entry.data)
        if self._history_cursors:
            new_data[DATA_HISTORY_CURSORS] = dict(self._history_cursors)
        else:
            new_data.pop(DATA_HISTORY_CURSORS, None)
        self.hass.config_entries.async_update_entry(self.entry, data=new_data)
        updated_entry = self.hass.config_entries.async_get_entry(self.entry.entry_id)
        if updated_entry is not None:
            self.entry = updated_entry
        self._history_cursors_dirty = False

    async def _async_store_measurements(
        self, slug: str, measurements: List[Dict[str, Any]], *, force: bool = False
    ) -> None:
        helper = self._helpers.get(slug)
        if not helper:
            return
        entity_id = self._entity_ids.get(slug) or helper.get("entity_id")
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
            if not measured_at or (not force and measured_at in recorded):
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
                time_fired_timestamp=dt_util.as_timestamp(dt_value),
            )
            events.append(event)
            recorded[measured_at] = None
            while len(recorded) > 200:
                recorded.popitem(last=False)
            previous_state = new_state

        if not events:
            return

        for event in events:
            instance._queue.put_nowait(event)
        await self._async_update_statistics(slug)

    async def _async_process_history_cursor(
        self,
        slug: str,
        helper: Dict[str, Any],
        *,
        force_reload: bool = False,
    ) -> None:
        if helper.get("entity_type") != "hassems":
            if slug in self._history_cursors:
                self._history_cursors.pop(slug, None)
                self._mark_history_cursors_dirty()
            return

        cursor = helper.get("history_cursor")
        if not cursor:
            if slug in self._history_cursors:
                self._history_cursors.pop(slug, None)
                self._mark_history_cursors_dirty()
            return

        cursor_str = str(cursor)
        stored = self._history_cursors.get(slug)
        if stored is None and not force_reload:
            self._history_cursors[slug] = cursor_str
            self._mark_history_cursors_dirty()
            return
        if stored == cursor_str and not force_reload:
            return

        success = await self._async_reload_history(slug)
        if not success:
            return
        if stored != cursor_str:
            self._history_cursors[slug] = cursor_str
            self._mark_history_cursors_dirty()

    async def _async_reload_history(self, slug: str) -> bool:
        helper = self._helpers.get(slug)
        if not helper:
            return False
        try:
            history = await self.client.async_get_history(slug, full=True)
        except HASSEMSAuthError as exc:
            raise ConfigEntryAuthFailed(str(exc)) from exc
        except HASSEMSError as exc:
            _LOGGER.warning("Unable to reload history for %s: %s", slug, exc)
            return False
        except Exception as exc:  # noqa: BLE001
            _LOGGER.warning("Unexpected error reloading history for %s: %s", slug, exc)
            return False

        normalized = self._normalize_history_records(history)
        self._history[slug] = normalized
        self._recorded_measurements.pop(slug, None)
        if normalized:
            await self._async_store_measurements(slug, normalized, force=True)
        await self._async_update_statistics(
            slug,
            full_refresh=True,
            history_override=normalized,
        )
        return True

    def _normalize_history_records(
        self, entries: List[Dict[str, Any]] | None
    ) -> List[Dict[str, Any]]:
        if not entries:
            return []
        dedup: Dict[str, Dict[str, Any]] = {}
        for item in entries:
            if not isinstance(item, dict):
                continue
            measured_at = item.get("measured_at")
            if not measured_at:
                continue
            key = str(measured_at)
            dedup[key] = {
                "measured_at": key,
                "value": item.get("value"),
            }
        ordered_keys = sorted(dedup)
        if len(ordered_keys) > MAX_HISTORY_POINTS:
            ordered_keys = ordered_keys[-MAX_HISTORY_POINTS:]
        return [dedup[key] for key in ordered_keys]

    async def _async_update_statistics(
        self,
        slug: str,
        *,
        full_refresh: bool = False,
        history_override: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        helper = self._helpers.get(slug)
        if not helper:
            return
        if helper.get("entity_type") != "hassems":
            return
        if helper.get("state_class") != "measurement":
            return
        entity_id = self._entity_ids.get(slug) or helper.get("entity_id")
        if not entity_id:
            return
        history = history_override if history_override is not None else self._history.get(slug)
        if not history:
            try:
                instance = recorder.get_instance(self.hass)
            except KeyError:
                return
            if not instance.is_running:
                return
            if full_refresh:
                await self.hass.async_add_executor_job(clear_statistics, instance, [entity_id])
            return
        points = self._parse_measurement_points(history)
        if not points:
            if full_refresh:
                try:
                    instance = recorder.get_instance(self.hass)
                except KeyError:
                    return
                if not instance.is_running:
                    return
                await self.hass.async_add_executor_job(clear_statistics, instance, [entity_id])
            return
        mode = str(helper.get("statistics_mode") or "linear").strip().lower()
        statistics = self._calculate_hourly_statistics(points, mode)
        try:
            instance = recorder.get_instance(self.hass)
        except KeyError:
            return
        if not instance.is_running:
            return
        if full_refresh:
            await self.hass.async_add_executor_job(clear_statistics, instance, [entity_id])
        if not statistics:
            return

        metadata: StatisticMetaData = {
            "statistic_id": entity_id,
            "source": DOMAIN,
            "name": helper.get("name"),
            "unit_of_measurement": helper.get("unit_of_measurement"),
            "has_sum": False,
            "mean_type": StatisticMeanType.ARITHMETIC,
            "unit_class": None,
        }
        async_add_external_statistics(self.hass, metadata, statistics)

    def _parse_measurement_points(
        self, history: List[Dict[str, Any]]
    ) -> List[Tuple[datetime, float]]:
        points: List[Tuple[datetime, float]] = []
        for item in history:
            measured_at = item.get("measured_at")
            if not measured_at:
                continue
            dt_value = dt_util.parse_datetime(measured_at)
            if dt_value is None:
                continue
            dt_value = dt_util.as_utc(dt_value)
            value = item.get("value")
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                continue
            if math.isnan(numeric) or math.isinf(numeric):
                continue
            points.append((dt_value, numeric))
        points.sort(key=lambda entry: entry[0])
        deduped: List[Tuple[datetime, float]] = []
        for dt_value, numeric in points:
            if deduped and dt_value == deduped[-1][0]:
                deduped[-1] = (dt_value, numeric)
            else:
                deduped.append((dt_value, numeric))
        return deduped

    def _calculate_hourly_statistics(
        self, points: List[Tuple[datetime, float]], mode: str
    ) -> List[StatisticData]:
        if not points:
            return []

        processed = list(points)
        normalized_mode = mode if mode in {"linear", "step"} else "linear"
        if normalized_mode == "step" and processed:
            now = dt_util.utcnow()
            last_time = processed[-1][0]
            if now > last_time:
                processed.append((now, processed[-1][1]))
        if len(processed) < 2:
            return []
        hour_stats: Dict[datetime, Dict[str, Any]] = {}
        for index in range(len(processed) - 1):
            start_time, start_value = processed[index]
            end_time, end_value = processed[index + 1]
            if end_time <= start_time:
                continue
            hour_cursor = start_time.replace(minute=0, second=0, microsecond=0)
            while hour_cursor < end_time:
                hour_end = hour_cursor + timedelta(hours=1)
                overlap_start = max(start_time, hour_cursor)
                overlap_end = min(end_time, hour_end)
                if overlap_end <= overlap_start:
                    hour_cursor = hour_end
                    continue
                value_start = self._value_at(
                    normalized_mode, start_time, start_value, end_time, end_value, overlap_start
                )
                value_end = self._value_at(
                    normalized_mode, start_time, start_value, end_time, end_value, overlap_end
                )
                duration = (overlap_end - overlap_start).total_seconds()
                if duration <= 0:
                    hour_cursor = hour_end
                    continue
                stats = hour_stats.setdefault(
                    hour_cursor,
                    {
                        "duration": 0.0,
                        "integral": 0.0,
                        "min": None,
                        "max": None,
                        "state": value_end,
                    },
                )
                average = (
                    (value_start + value_end) / 2.0
                    if normalized_mode == "linear"
                    else value_start
                )
                stats["duration"] += duration
                stats["integral"] += average * duration
                for candidate in (value_start, value_end):
                    if stats["min"] is None or candidate < stats["min"]:
                        stats["min"] = candidate
                    if stats["max"] is None or candidate > stats["max"]:
                        stats["max"] = candidate
                stats["state"] = value_end
                hour_cursor = hour_end

        statistics: List[StatisticData] = []
        for hour_start in sorted(hour_stats):
            stats = hour_stats[hour_start]
            duration = stats["duration"]
            if duration <= 0:
                continue
            min_value = stats["min"]
            max_value = stats["max"]
            state_value = stats["state"]
            if min_value is None or max_value is None or state_value is None:
                continue
            mean_value = stats["integral"] / duration if duration else 0.0
            statistics.append(
                {
                    "start": hour_start,
                    "mean": mean_value,
                    "min": min_value,
                    "max": max_value,
                    "state": state_value,
                }
            )
        return statistics

    @staticmethod
    def _value_at(
        mode: str,
        start_time: datetime,
        start_value: float,
        end_time: datetime,
        end_value: float,
        point_time: datetime,
    ) -> float:
        if mode == "step":
            if point_time >= end_time:
                return float(end_value)
            return float(start_value)
        total = (end_time - start_time).total_seconds()
        if total <= 0:
            return float(end_value)
        offset = (point_time - start_time).total_seconds()
        ratio = max(0.0, min(1.0, offset / total))
        return float(start_value + (end_value - start_value) * ratio)
