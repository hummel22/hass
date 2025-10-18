from __future__ import annotations

import asyncio
import json
import logging
import math
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from aiohttp import web
from homeassistant import config_entries
from homeassistant.components import recorder
from homeassistant.components.recorder.db_schema import (
    EventData,
    Events,
    EventTypes,
    StateAttributes,
    States,
    StatesMeta,
)
from homeassistant.components.recorder.statistics import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
    async_add_external_statistics,
    clear_statistics,
)
from homeassistant.components.recorder.util import session_scope
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    ATTR_ENTITY_ID,
    ATTR_UNIT_OF_MEASUREMENT,
    EVENT_STATE_CHANGED,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import HASSEMSAuthError, HASSEMSError, HASSEMSClient
from .const import (
    ATTR_HISTORY,
    ATTR_HISTORY_CURSOR,
    ATTR_LAST_MEASURED,
    ATTR_STATE_CLASS,
    CONF_INCLUDED_ENTITIES,
    CONF_IGNORED_ENTITIES,
    DATA_HISTORY_CURSORS,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    EVENT_ENTITY_CREATED,
    EVENT_ENTITY_DELETED,
    EVENT_ENTITY_UPDATED,
    EVENT_ENTITY_VALUE,
    SIGNAL_ENTITY_ADDED,
    SIGNAL_ENTITY_REMOVED,
    SIGNAL_ENTITY_UPDATED,
)

_LOGGER = logging.getLogger(__name__)

MAX_HISTORY_POINTS = 10000
HISTORY_HORIZON_DAYS = 10


def _coerce_previous_state(
    last_state: Optional[States],
    states_meta: StatesMeta,
    entity_id: str,
) -> Tuple[Optional[Dict[str, Any]], Optional[str], Optional[float]]:
    """Convert a recorder row into a dictionary without requiring a stored entity id."""

    if last_state is None:
        return None, None, None

    try:
        last_state_obj = last_state.to_native(validate_entity_id=False)
    except ValueError:
        fallback_entity_id = (
            getattr(last_state, "entity_id", None)
            or getattr(states_meta, "entity_id", None)
            or entity_id
        )

        if not fallback_entity_id:
            _LOGGER.debug(
                "Discarding recorder state %s because entity_id is missing",
                getattr(last_state, "state_id", None),
            )
            return None, None, None

        attributes: Dict[str, Any] = {}
        if hasattr(last_state, "attributes_as_dict"):
            try:
                attributes = last_state.attributes_as_dict  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001
                _LOGGER.debug(
                    "Failed to decode attributes for recorder state %s",
                    getattr(last_state, "state_id", None),
                    exc_info=True,
                )

        last_changed_ts = getattr(last_state, "last_changed_ts", None)
        if last_changed_ts is None:
            last_changed_ts = getattr(last_state, "last_updated_ts", None)

        last_updated_ts = getattr(last_state, "last_updated_ts", None)

        def _iso(ts: Optional[float]) -> Optional[str]:
            if ts is None:
                return None
            converter = getattr(dt_util, "utc_from_timestamp", None)
            if callable(converter):
                dt_value = converter(ts)
            else:
                dt_value = datetime.fromtimestamp(ts, tz=timezone.utc)
            return dt_value.isoformat()

        last_changed_iso = _iso(last_changed_ts)
        last_updated_iso = _iso(last_updated_ts) or last_changed_iso

        previous_state_dict = {
            "entity_id": fallback_entity_id,
            "state": getattr(last_state, "state", None),
            "attributes": attributes,
            "last_changed": last_changed_iso,
            "last_updated": last_updated_iso,
        }

        _LOGGER.debug(
            "Recovered recorder state %s using metadata entity_id %s",
            getattr(last_state, "state_id", None),
            fallback_entity_id,
        )

        return previous_state_dict, getattr(last_state, "state", None), last_changed_ts

    last_changed_ts = (
        last_state.last_changed_ts
        if last_state.last_changed_ts is not None
        else last_state.last_updated_ts
    )
    return last_state_obj.as_dict(), last_state_obj.state, last_changed_ts


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
        self._entities: Dict[str, Dict[str, Any]] = {}
        self._history: Dict[str, List[Dict[str, Any]]] = {}
        # _recorded_measurements only keeps diagnostic recorded_at markers to avoid
        # reprocessing the same payload; business logic must rely on measured_at.
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
        self._included: Set[str] = set(entry.options.get(CONF_INCLUDED_ENTITIES, []))
        self._ignored: Set[str] = set(entry.options.get(CONF_IGNORED_ENTITIES, []))
        self._subscription_id: Optional[int] = entry.data.get("subscription_id")

        self.signal_add = SIGNAL_ENTITY_ADDED.format(entry_id=entry.entry_id)
        self.signal_remove = SIGNAL_ENTITY_REMOVED.format(entry_id=entry.entry_id)
        self.signal_update = SIGNAL_ENTITY_UPDATED.format(entry_id=entry.entry_id)

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
            included=set(entry.options.get(CONF_INCLUDED_ENTITIES, [])),
            ignored=set(entry.options.get(CONF_IGNORED_ENTITIES, [])),
        )
        self.reapply_filters()
        await self.async_request_refresh()

    def reapply_filters(self) -> None:
        allowed_slugs = self._select_allowed_slugs(self._entities)
        allowed_set = set(allowed_slugs)
        current = dict(self.data or {})
        updated = {
            slug: self._entities[slug]
            for slug in allowed_slugs
            if slug in self._entities
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
            entities = await self.client.async_list_entities()
        except HASSEMSAuthError as exc:
            raise ConfigEntryAuthFailed(str(exc)) from exc
        except HASSEMSError as exc:
            raise UpdateFailed(str(exc)) from exc

        _LOGGER.debug("Fetched %s entities from HASSEMS", len(entities))
        mapping: Dict[str, Dict[str, Any]] = {
            entity["slug"]: entity for entity in entities if entity.get("slug")
        }
        self._entities = mapping

        allowed_slugs = self._select_allowed_slugs(mapping)
        _LOGGER.debug(
            "Allowed slugs after filter application: %s", ", ".join(allowed_slugs)
        )
        current_slugs = set(self.data or {})
        added = [slug for slug in allowed_slugs if slug not in current_slugs]
        removed = [slug for slug in current_slugs if slug not in allowed_slugs]

        if added or removed:
            _LOGGER.debug("Entity set changes - added: %s removed: %s", added, removed)

        await self._fetch_history_for_new(added)

        data = {slug: mapping[slug] for slug in allowed_slugs}
        self._history = {slug: self._history.get(slug, []) for slug in allowed_slugs}
        self._recorded_measurements = {
            slug: self._recorded_measurements.get(slug, OrderedDict())
            for slug in allowed_slugs
        }

        for slug in allowed_slugs:
            entity_data = mapping[slug]
            await self._async_process_history_cursor(slug, entity_data)

        removed_cursor_slugs = [
            slug for slug in list(self._history_cursors) if slug not in mapping
        ]
        for slug in removed_cursor_slugs:
            self._history_cursors.pop(slug, None)
            self._mark_history_cursors_dirty()
            _LOGGER.debug(
                "Removed stored history cursor for %s because entity no longer exists",
                slug,
            )
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
        _LOGGER.debug("Fetching historic data for new entities: %s", slugs)
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
                entity_id = self._statistics_entity_id(slug)
                normalized = self._normalize_history_records(
                    result,
                    slug=slug,
                    entity_id=entity_id,
                )
                self._history[slug] = normalized
                _LOGGER.debug(
                    "Loaded %s normalized history records for %s (entity_id=%s)",
                    len(normalized),
                    slug,
                    entity_id,
                )
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
            entity_id = self._statistics_entity_id(slug)
            normalized = self._normalize_history_records(
                history,
                slug=slug,
                entity_id=entity_id,
            )
            self._history[slug] = normalized
            if normalized:
                _LOGGER.debug(
                    "Fetched %s history points on-demand for %s (entity_id=%s)",
                    len(normalized),
                    slug,
                    entity_id,
                )
                await self._async_store_measurements(slug, normalized)
        return list(self._history.get(slug, []))

    async def async_set_entity_value(self, slug: str, value: Any) -> None:
        try:
            await self.client.async_set_value(slug, value)
        except HASSEMSAuthError as exc:
            raise ConfigEntryAuthFailed(str(exc)) from exc
        except HASSEMSError as exc:
            raise HomeAssistantError(str(exc)) from exc
        _LOGGER.debug("Set value %s for %s via HASSEMS API", value, slug)

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
        _LOGGER.debug(
            "Received webhook event %s (webhook_id=%s) with payload keys: %s",
            event,
            webhook_id,
            list(payload.keys()),
        )
        await self._async_process_event(event, payload)
        return web.Response(status=200)

    async def _async_process_event(self, event: str, payload: Dict[str, Any]) -> None:
        entity = payload.get("entity") or {}
        slug = entity.get("slug")
        if not slug:
            return

        _LOGGER.debug(
            "Processing event %s for %s with history_cursor=%s",
            event,
            slug,
            entity.get("history_cursor"),
        )

        if event == EVENT_ENTITY_DELETED:
            self._entities.pop(slug, None)
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

        self._entities[slug] = entity
        self._pending_discoveries.discard(slug)

        if event == EVENT_ENTITY_VALUE:
            data_payload = payload.get("data") or {}
            measurement = data_payload.get("measured_at")
            value = data_payload.get("value")
            historic_flag = bool(data_payload.get("historic"))
            cursor_override = data_payload.get("historic_cursor")
            recorded_at = data_payload.get("recorded_at")
            _LOGGER.debug(
                "Received measurement for %s - measured_at=%s value=%s historic=%s cursor=%s",
                slug,
                measurement,
                value,
                historic_flag,
                cursor_override or entity.get("history_cursor"),
            )
            history = self._history.setdefault(slug, [])
            history.append({
                "value": value,
                "measured_at": measurement,
                "recorded_at": recorded_at,
                "historic": historic_flag,
                "historic_cursor": cursor_override or entity.get("history_cursor"),
                "history_cursor": entity.get("history_cursor"),
            })
            if len(history) > MAX_HISTORY_POINTS:
                del history[:-MAX_HISTORY_POINTS]
            if measurement:
                await self._async_store_measurements(slug, [history[-1]])

        await self._async_process_history_cursor(slug, entity)
        self._save_history_cursors_if_needed()

        allowed_slugs = set(self._select_allowed_slugs(self._entities))
        if slug not in allowed_slugs:
            await self._async_prompt_discovery(entity)
            return

        existed = slug in (self.data or {})
        new_data = dict(self.data or {})
        new_data[slug] = entity
        self.async_set_updated_data(new_data)
        if existed:
            async_dispatcher_send(self.hass, self.signal_update, slug)
        else:
            async_dispatcher_send(self.hass, self.signal_add, slug)

    async def _async_prompt_discovery(self, entity: Dict[str, Any]) -> None:
        slug = entity.get("slug")
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
                data={"entity": entity},
            )
        )

    def entity(self, slug: str) -> Optional[Dict[str, Any]]:
        if self.data:
            return self.data.get(slug)
        return None

    def entity_history(self, slug: str) -> List[Dict[str, Any]]:
        return list(self._history.get(slug, []))

    def register_entity(self, slug: str, entity_id: str | None) -> None:
        if not entity_id:
            return
        self._entity_ids[slug] = entity_id
        if self._history.get(slug):
            self.hass.async_create_task(
                self._async_backfill_history_for_entity(slug)
            )

    def unregister_entity(self, slug: str) -> None:
        self._entity_ids.pop(slug, None)

    def _statistics_entity_id(self, slug: str) -> str | None:
        entity_id = self._entity_ids.get(slug)
        if not entity_id:
            return None
        domain, sep, object_id = entity_id.partition(".")
        if sep != "." or not domain or not object_id:
            return None
        if domain not in {"sensor", "number"}:
            return None
        return entity_id

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

    async def _async_backfill_history_for_entity(self, slug: str) -> None:
        history = self._history.get(slug)
        if not history:
            return
        await self._async_store_measurements(slug, history, force=True)

    async def _async_store_measurements(
        self, slug: str, measurements: List[Dict[str, Any]], *, force: bool = False
    ) -> None:
        entity = self._entities.get(slug)
        if not entity:
            return
        entity_id = self._statistics_entity_id(slug)
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

        # recorded_at markers are diagnostic only; use measured_at for decisions.
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
            if (unit := entity.get("unit_of_measurement")) is not None:
                base_attributes[ATTR_UNIT_OF_MEASUREMENT] = unit
            if (device_class := entity.get("device_class")) is not None:
                base_attributes[ATTR_DEVICE_CLASS] = device_class
            if (state_class := entity.get("state_class")) is not None:
                base_attributes[ATTR_STATE_CLASS] = state_class
            if (icon := entity.get("icon")) is not None:
                base_attributes["icon"] = icon

        _LOGGER.debug(
            "Processing %s measurements for %s (entity_id=%s force=%s)",
            len(measurements),
            slug,
            entity_id,
            force,
        )
        start_dt, end_dt = self._history_window(measurements)
        if start_dt and end_dt:
            historic_count = sum(1 for item in measurements if item.get("historic"))
            _LOGGER.debug(
                "Measurement window for %s spans %s to %s (%s/%s historic entries)",
                slug,
                start_dt.isoformat(),
                end_dt.isoformat(),
                historic_count,
                len(measurements),
            )

        entries_states_only: List[Dict[str, Any]] = []
        processed_for_statistics = False

        now_local = dt_util.now()
        today_local = now_local.date()
        historic_cutoff = dt_util.utcnow() - timedelta(days=HISTORY_HORIZON_DAYS)

        for item in sorted(
            measurements, key=lambda entry: entry.get("measured_at") or ""
        ):
            measured_at = item.get("measured_at")
            if not measured_at or (not force and measured_at in recorded):
                _LOGGER.debug(
                    "Skipping measurement for %s (measured_at=%s) - force=%s already_recorded=%s",
                    slug,
                    measured_at,
                    force,
                    measured_at in recorded if measured_at else False,
                )
                continue
            dt_value = dt_util.parse_datetime(measured_at)
            if dt_value is None:
                _LOGGER.debug(
                    "Unable to parse measured_at for %s: %s", slug, measured_at
                )
                continue
            dt_value = dt_util.as_utc(dt_value)
            measured_local = dt_util.as_local(dt_value)
            measured_date = measured_local.date()

            state_value = item.get("value")
            state_str = "" if state_value is None else str(state_value)

            attributes = dict(base_attributes)
            attributes.pop(ATTR_HISTORY, None)
            attributes[ATTR_LAST_MEASURED] = measured_at
            historic_cursor = item.get("historic_cursor") or item.get("history_cursor")
            if historic_cursor:
                attributes[ATTR_HISTORY_CURSOR] = historic_cursor
            if "historic" in item:
                attributes["historic"] = bool(item.get("historic"))

            if measured_date == today_local:
                recorded[measured_at] = None
                while len(recorded) > 200:
                    recorded.popitem(last=False)
                _LOGGER.debug(
                    "Ignoring %s measurement at %s for statistics - occurs today",
                    slug,
                    measured_at,
                )
                continue

            if dt_value >= historic_cutoff:
                entries_states_only.append(
                    {
                        "timestamp": dt_value,
                        "state": state_str,
                        "attributes": attributes,
                    }
                )
                processed_for_statistics = True
            else:
                processed_for_statistics = True

            recorded[measured_at] = None
            while len(recorded) > 200:
                recorded.popitem(last=False)

            _LOGGER.debug(
                "Prepared measurement for %s at %s (historic=%s cursor=%s)",
                slug,
                measured_at,
                item.get("historic"),
                historic_cursor,
            )

        if entries_states_only:
            _LOGGER.debug(
                "Writing %s historic measurements for %s to recorder",
                len(entries_states_only),
                slug,
            )
            try:
                await self.hass.async_add_executor_job(
                    self._write_measurements_direct,
                    instance,
                    entity_id,
                    entries_states_only,
                    True,
                )
            except Exception as err:  # noqa: BLE001
                _LOGGER.error(
                    "Error writing historic measurements for %s (%s rows) to recorder: %s",
                    slug,
                    len(entries_states_only),
                    err,
                    exc_info=True,
                )
                raise
            else:
                _LOGGER.debug(
                    "Finished writing %s historic measurements for %s",
                    len(entries_states_only),
                    slug,
                )

        if processed_for_statistics:
            _LOGGER.debug("Triggering statistics refresh for %s", slug)
            await self._async_update_statistics(slug)

    def _write_measurements_direct(
        self,
        instance: recorder.Recorder,
        entity_id: str,
        entries: List[Dict[str, Any]],
        states_only: bool = False,
    ) -> None:
        if not entries:
            return

        session = instance.get_session()
        try:
            with session_scope(session=session) as scoped_session:
                if not states_only:
                    event_type = (
                        scoped_session.query(EventTypes)
                        .filter(EventTypes.event_type == EVENT_STATE_CHANGED)
                        .one_or_none()
                    )
                    if event_type is None:
                        event_type = EventTypes(event_type=EVENT_STATE_CHANGED)
                        scoped_session.add(event_type)
                        scoped_session.flush()
                else:
                    event_type = None
    
                states_meta = (
                    scoped_session.query(StatesMeta)
                    .filter(StatesMeta.entity_id == entity_id)
                    .one_or_none()
                )
                if states_meta is None:
                    states_meta = StatesMeta(entity_id=entity_id)
                    scoped_session.add(states_meta)
                    scoped_session.flush()
    
                metadata_id = states_meta.metadata_id
    
                last_state = (
                    scoped_session.query(States)
                    .filter(States.metadata_id == metadata_id)
                    .order_by(States.last_updated_ts.desc())
                    .limit(1)
                    .one_or_none()
                )
    
                (
                    previous_state_dict,
                    previous_state_value,
                    previous_last_changed_ts,
                ) = _coerce_previous_state(last_state, states_meta, entity_id)
                previous_state_id = last_state.state_id if last_state is not None else None
                if previous_state_value is None and last_state is not None:
                    previous_state_value = last_state.state
                if previous_last_changed_ts is None and last_state is not None:
                    if last_state.last_changed_ts is not None:
                        previous_last_changed_ts = last_state.last_changed_ts
                    else:
                        previous_last_changed_ts = last_state.last_updated_ts

                for entry in entries:
                    timestamp: datetime = dt_util.as_utc(entry["timestamp"])
                    timestamp_ts = dt_util.utc_to_timestamp(timestamp)
                    state_str: str = entry["state"]
                    attributes: Dict[str, Any] = entry["attributes"]
    
                    if (
                        previous_state_value is not None
                        and previous_state_value == state_str
                        and previous_last_changed_ts is not None
                    ):
                        last_changed_ts = previous_last_changed_ts
                    else:
                        last_changed_ts = timestamp_ts
    
                    last_changed_dt = dt_util.utc_from_timestamp(last_changed_ts)
                    new_state_dict = {
                        "entity_id": entity_id,
                        "state": state_str,
                        "attributes": attributes,
                        "last_changed": last_changed_dt.isoformat(),
                        "last_updated": timestamp.isoformat(),
                    }
    
                    if not states_only and event_type is not None:
                        event_data = {
                            ATTR_ENTITY_ID: entity_id,
                            "old_state": previous_state_dict,
                            "new_state": new_state_dict,
                        }
    
                        event_data_row = EventData(
                            hash=None,
                            shared_data=json.dumps(
                                event_data, sort_keys=True, default=str
                            ),
                        )
                        scoped_session.add(event_data_row)
                        scoped_session.flush()
    
                        event_row = Events(
                            event_type=None,
                            event_data=None,
                            origin=None,
                            origin_idx=1,
                            time_fired=timestamp,
                            time_fired_ts=timestamp_ts,
                            context_id=None,
                            context_user_id=None,
                            context_parent_id=None,
                            data_id=event_data_row.data_id,
                            context_id_bin=None,
                            context_user_id_bin=None,
                            context_parent_id_bin=None,
                            event_type_id=event_type.event_type_id,
                        )
                        scoped_session.add(event_row)
                        scoped_session.flush()
                        event_id = event_row.event_id
                    else:
                        event_id = None
    
                    attributes_row = StateAttributes(
                        hash=None,
                        shared_attrs=json.dumps(attributes, sort_keys=True, default=str),
                    )
                    scoped_session.add(attributes_row)
                    scoped_session.flush()
    
                    states_row = States(
                        entity_id=entity_id,
                        state=state_str,
                        attributes=None,
                        event_id=event_id,
                        last_changed=None,
                        last_changed_ts=None
                        if last_changed_ts == timestamp_ts
                        else last_changed_ts,
                        last_updated=None,
                        last_updated_ts=timestamp_ts,
                        old_state_id=previous_state_id,
                        attributes_id=attributes_row.attributes_id,
                        context_id=None,
                        context_user_id=None,
                        context_parent_id=None,
                        origin_idx=1,
                        context_id_bin=None,
                        context_user_id_bin=None,
                        context_parent_id_bin=None,
                        metadata_id=metadata_id,
                    )
                    scoped_session.add(states_row)
                    scoped_session.flush()
    
                    previous_state_dict = new_state_dict
                    previous_state_id = states_row.state_id
                    previous_state_value = state_str
                    previous_last_changed_ts = last_changed_ts
        except Exception as err:  # noqa: BLE001
            _LOGGER.error(
                "Error while writing %s recorder rows for %s: %s",
                len(entries),
                entity_id,
                err,
                exc_info=True,
            )
            raise

    async def _async_process_history_cursor(
        self,
        slug: str,
        entity: Dict[str, Any],
        *,
        force_reload: bool = False,
    ) -> None:
        if entity.get("entity_type") != "hassems":
            if slug in self._history_cursors:
                self._history_cursors.pop(slug, None)
                self._mark_history_cursors_dirty()
                _LOGGER.debug(
                    "Cleared history cursor for %s because entity type is %s",
                    slug,
                    entity.get("entity_type"),
                )
            return

        cursor = entity.get("history_cursor")
        if not cursor:
            if slug in self._history_cursors:
                self._history_cursors.pop(slug, None)
                self._mark_history_cursors_dirty()
                _LOGGER.debug("Cleared history cursor for %s because cursor missing", slug)
            return

        cursor_str = str(cursor)
        stored = self._history_cursors.get(slug)
        _LOGGER.debug(
            "Evaluating history cursor for %s - incoming=%s stored=%s force_reload=%s",
            slug,
            cursor_str,
            stored,
            force_reload,
        )
        if stored is None and not force_reload:
            self._history_cursors[slug] = cursor_str
            self._mark_history_cursors_dirty()
            _LOGGER.debug(
                "Stored initial history cursor for %s: %s", slug, cursor_str
            )
            return
        if stored == cursor_str and not force_reload:
            _LOGGER.debug("History cursor unchanged for %s; skipping reload", slug)
            return

        success = await self._async_reload_history(slug)
        if not success:
            _LOGGER.debug("History reload failed for %s", slug)
            return
        if stored != cursor_str:
            self._history_cursors[slug] = cursor_str
            self._mark_history_cursors_dirty()
            _LOGGER.debug(
                "Updated stored history cursor for %s to %s", slug, cursor_str
            )

    async def _async_reload_history(self, slug: str) -> bool:
        entity = self._entities.get(slug)
        if not entity:
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

        entity_id = self._statistics_entity_id(slug)
        normalized = self._normalize_history_records(
            history,
            slug=slug,
            entity_id=entity_id,
        )
        self._history[slug] = normalized
        self._recorded_measurements.pop(slug, None)
        _LOGGER.debug(
            "Reloaded history for %s (entity_id=%s) with %s records",
            slug,
            entity_id,
            len(normalized),
        )
        history_list = history or []
        start_dt, end_dt = self._history_window(history_list)
        cursor_hint = entity.get("history_cursor")
        if start_dt and end_dt:
            _LOGGER.debug(
                "HASSEMS history fetch for %s (entity_id=%s) returned %s rows covering %s to %s (cursor=%s)",
                slug,
                entity_id,
                len(history_list),
                start_dt.isoformat(),
                end_dt.isoformat(),
                cursor_hint,
            )
        else:
            _LOGGER.debug(
                "HASSEMS history fetch for %s (entity_id=%s) returned %s rows without timestamps (cursor=%s)",
                slug,
                entity_id,
                len(history_list),
                cursor_hint,
            )
        if normalized:
            await self._async_store_measurements(slug, normalized, force=True)
        await self._async_update_statistics(
            slug,
            full_refresh=True,
            history_override=normalized,
        )
        _LOGGER.debug(
            "Completed history reload workflow for %s (entity_id=%s)",
            slug,
            entity_id,
        )
        return True

    def _normalize_history_records(
        self,
        entries: List[Dict[str, Any]] | None,
        *,
        slug: str | None = None,
        entity_id: str | None = None,
    ) -> List[Dict[str, Any]]:
        if not entries:
            return []
        if slug and entity_id is None:
            entity_id = self._statistics_entity_id(slug)
        _LOGGER.debug(
            "Normalizing %s history entries for %s (entity_id=%s)",
            len(entries),
            slug or "<unknown>",
            entity_id or "<unknown>",
        )
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
                "recorded_at": item.get("recorded_at"),
                "historic": bool(item.get("historic")),
                "historic_cursor": item.get("historic_cursor")
                or item.get("history_cursor"),
                "history_cursor": item.get("history_cursor")
                or item.get("historic_cursor"),
            }
        ordered_keys = sorted(dedup)
        if len(ordered_keys) > MAX_HISTORY_POINTS:
            ordered_keys = ordered_keys[-MAX_HISTORY_POINTS:]
            _LOGGER.debug(
                "Truncated normalized history for %s (entity_id=%s) to last %s points",
                slug or "<unknown>",
                entity_id or "<unknown>",
                len(ordered_keys),
            )
        if ordered_keys:
            _LOGGER.debug(
                "Normalized history window for %s (entity_id=%s) spans %s to %s (%s unique points)",
                slug or "<unknown>",
                entity_id or "<unknown>",
                ordered_keys[0],
                ordered_keys[-1],
                len(ordered_keys),
            )
        return [dedup[key] for key in ordered_keys]

    async def _async_update_statistics(
        self,
        slug: str,
        *,
        full_refresh: bool = False,
        history_override: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        entity = self._entities.get(slug)
        if not entity:
            return
        if entity.get("entity_type") != "hassems":
            return
        if entity.get("state_class") != "measurement":
            return
        entity_id = self._statistics_entity_id(slug)
        if not entity_id:
            return
        _LOGGER.debug(
            "Updating statistics for %s (entity_id=%s full_refresh=%s history_override=%s)",
            slug,
            entity_id,
            full_refresh,
            history_override is not None,
        )
        history = history_override if history_override is not None else self._history.get(slug)
        if history:
            hist_start, hist_end = self._history_window(history)
            if hist_start and hist_end:
                _LOGGER.debug(
                    "Statistics history window for %s (entity_id=%s) spans %s to %s (%s records)",
                    slug,
                    entity_id,
                    hist_start.isoformat(),
                    hist_end.isoformat(),
                    len(history),
                )
        if not history:
            try:
                instance = recorder.get_instance(self.hass)
            except KeyError:
                return
            if not instance.is_running:
                return
            if full_refresh:
                await self.hass.async_add_executor_job(clear_statistics, instance, [entity_id])
                _LOGGER.debug(
                    "Cleared statistics for %s (entity_id=%s) because no history available",
                    slug,
                    entity_id,
                )
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
                _LOGGER.debug(
                    "Cleared statistics for %s (entity_id=%s) because no valid points were parsed",
                    slug,
                    entity_id,
                )
            return
        mode = str(entity.get("statistics_mode") or "linear").strip().lower()
        _LOGGER.debug(
            "Calculating statistics for %s (entity_id=%s) using mode=%s with %s points",
            slug,
            entity_id,
            mode,
            len(points),
        )
        if points:
            _LOGGER.debug(
                "Measurement points for %s (entity_id=%s) cover %s to %s",
                slug,
                entity_id,
                points[0][0].isoformat(),
                points[-1][0].isoformat(),
            )
        statistics = self._calculate_hourly_statistics(
            points,
            mode,
            history_window=(hist_start, hist_end),
        )
        stats_count = len(statistics)
        if statistics:
            stats_start = statistics[0]["start"].isoformat()
            stats_end = statistics[-1]["start"].isoformat()
            _LOGGER.debug(
                "Computed %s hourly statistics rows for %s (entity_id=%s) covering %s to %s (mode=%s)",
                stats_count,
                slug,
                entity_id,
                stats_start,
                stats_end,
                mode,
            )
        else:
            _LOGGER.debug(
                "No hourly statistics rows computed for %s (entity_id=%s) using mode=%s",
                slug,
                entity_id,
                mode,
            )
        try:
            instance = recorder.get_instance(self.hass)
        except KeyError:
            return
        if not instance.is_running:
            return
        if full_refresh:
            await self.hass.async_add_executor_job(clear_statistics, instance, [entity_id])
            _LOGGER.debug(
                "Cleared existing statistics for %s (entity_id=%s) before reload",
                slug,
                entity_id,
            )
        if not statistics:
            _LOGGER.debug(
                "No statistics generated for %s (entity_id=%s); skipping submission",
                slug,
                entity_id,
            )
            return

        metadata: StatisticMetaData = {
            "statistic_id": entity_id,
            "source": DOMAIN,
            "name": entity.get("name"),
            "unit_of_measurement": entity.get("unit_of_measurement"),
            "has_sum": False,
            "mean_type": StatisticMeanType.ARITHMETIC,
            "unit_class": None,
        }
        _LOGGER.debug(
            "Submitting %s statistics rows for %s (entity_id=%s mode=%s)",
            stats_count,
            slug,
            entity_id,
            mode,
        )
        first_start = statistics[0]["start"].isoformat()
        last_start = statistics[-1]["start"].isoformat()
        _LOGGER.debug(
            "Submitting statistics window for %s (entity_id=%s) covering %s to %s",
            slug,
            entity_id,
            first_start,
            last_start,
        )
        try:
            _LOGGER.debug(
                "Writing %s long-term statistics rows for %s (entity_id=%s mode=%s) to recorder",
                stats_count,
                slug,
                entity_id,
                mode,
            )
            async_add_external_statistics(self.hass, metadata, statistics)
        except Exception as err:  # noqa: BLE001
            _LOGGER.error(
                "Error writing long-term statistics for %s (entity_id=%s mode=%s): %s",
                slug,
                entity_id,
                mode,
                err,
                exc_info=True,
            )
            raise
        else:
            _LOGGER.debug(
                "Finished writing %s long-term statistics rows for %s (entity_id=%s mode=%s)",
                stats_count,
                slug,
                entity_id,
                mode,
            )

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
                _LOGGER.debug(
                    "Ignoring history entry with unparsable timestamp for statistics: %s",
                    item,
                )
                continue
            dt_value = dt_util.as_utc(dt_value)
            value = item.get("value")
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                _LOGGER.debug(
                    "Ignoring non-numeric history entry for statistics: %s", item
                )
                continue
            if math.isnan(numeric) or math.isinf(numeric):
                _LOGGER.debug(
                    "Ignoring invalid numeric value for statistics: %s", item
                )
                continue
            points.append((dt_value, numeric))
        points.sort(key=lambda entry: entry[0])
        deduped: List[Tuple[datetime, float]] = []
        for dt_value, numeric in points:
            if deduped and dt_value == deduped[-1][0]:
                deduped[-1] = (dt_value, numeric)
            else:
                deduped.append((dt_value, numeric))
        _LOGGER.debug(
            "Prepared %s measurement points for statistics", len(deduped)
        )
        return deduped

    def _calculate_hourly_statistics(
        self,
        points: List[Tuple[datetime, float]],
        mode: str,
        history_window: Tuple[datetime | None, datetime | None] | None = None,
    ) -> List[StatisticData]:
        if not points:
            return []

        processed = list(points)
        normalized_mode = mode if mode in {"linear", "step", "point"} else "linear"
        start_anchor = processed[0][0]
        end_anchor = processed[-1][0]
        if history_window is not None:
            window_start, window_end = history_window
            if window_start is not None:
                start_anchor = window_start
            if window_end is not None:
                end_anchor = window_end
        start_hour = start_anchor.replace(minute=0, second=0, microsecond=0)
        if end_anchor > start_anchor:
            effective_end = end_anchor - timedelta(microseconds=1)
        else:
            effective_end = end_anchor
        end_hour = effective_end.replace(minute=0, second=0, microsecond=0)
        if end_hour < start_hour:
            end_hour = start_hour
        if normalized_mode == "point":
            hour_buckets: Dict[datetime, Dict[str, Any]] = {}
            for timestamp, value in processed:
                hour_start = timestamp.replace(minute=0, second=0, microsecond=0)
                stats = hour_buckets.setdefault(
                    hour_start,
                    {
                        "values": [],
                        "state": None,
                    },
                )
                stats["values"].append(value)
                stats["state"] = value

            statistics: List[StatisticData] = []
            for hour_start in sorted(hour_buckets):
                stats = hour_buckets[hour_start]
                values = stats["values"]
                if not values:
                    continue
                state_value = stats["state"]
                if state_value is None:
                    continue
                statistics.append(
                    {
                        "start": hour_start,
                        "mean": sum(values) / len(values),
                        "min": min(values),
                        "max": max(values),
                        "state": state_value,
                    }
                )
            if statistics:
                filled: Dict[datetime, StatisticData] = {
                    stat["start"]: stat for stat in statistics
                }
            else:
                filled = {}
            cursor = start_hour
            while cursor <= end_hour:
                if cursor not in filled:
                    filled[cursor] = {
                        "start": cursor,
                        "mean": 0.0,
                        "min": 0.0,
                        "max": 0.0,
                        "state": 0.0,
                    }
                cursor += timedelta(hours=1)
            statistics = [
                filled_hour
                for filled_hour in sorted(filled.values(), key=lambda item: item["start"])
            ]
            return statistics
        if normalized_mode == "step" and processed:
            now = dt_util.utcnow()
            last_time = processed[-1][0]
            if now > last_time:
                processed.append((now, processed[-1][1]))
        if normalized_mode == "step" and len(processed) == 1:
            statistics: List[StatisticData] = []
            cursor = start_hour
            single_value = float(processed[0][1])
            while cursor <= end_hour:
                statistics.append(
                    {
                        "start": cursor,
                        "mean": single_value,
                        "min": single_value,
                        "max": single_value,
                        "state": single_value,
                    }
                )
                cursor += timedelta(hours=1)
            return statistics
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
        if statistics:
            _LOGGER.debug(
                "Calculated %s statistics buckets for mode=%s spanning %s to %s",
                len(statistics),
                normalized_mode,
                statistics[0]["start"].isoformat(),
                statistics[-1]["start"].isoformat(),
            )
        statistics = [
            stat
            for stat in statistics
            if start_hour <= stat["start"] <= end_hour
        ]
        stats_by_hour: Dict[datetime, StatisticData] = {
            stat["start"]: stat for stat in statistics
        }
        cursor = start_hour
        while cursor <= end_hour:
            if cursor not in stats_by_hour:
                if normalized_mode == "linear":
                    interpolated = self._interpolate_linear_hour(
                        processed, cursor, cursor + timedelta(hours=1)
                    )
                else:
                    interpolated = self._interpolate_step_hour(
                        processed, cursor, cursor + timedelta(hours=1)
                    )
                if interpolated is not None:
                    stats_by_hour[cursor] = interpolated
            cursor += timedelta(hours=1)
        if stats_by_hour:
            statistics = [
                stats_by_hour[hour]
                for hour in sorted(stats_by_hour, key=lambda item: item)
            ]
        return statistics

    def _interpolate_linear_hour(
        self,
        points: List[Tuple[datetime, float]],
        hour_start: datetime,
        hour_end: datetime,
    ) -> StatisticData | None:
        if not points:
            return None
        if len(points) == 1:
            value = float(points[0][1])
            return {
                "start": hour_start,
                "mean": value,
                "min": value,
                "max": value,
                "state": value,
            }
        start_value = self._linear_value_from_points(points, hour_start)
        end_value = self._linear_value_from_points(points, hour_end)
        min_value = min(start_value, end_value)
        max_value = max(start_value, end_value)
        mean_value = (start_value + end_value) / 2.0
        return {
            "start": hour_start,
            "mean": mean_value,
            "min": min_value,
            "max": max_value,
            "state": end_value,
        }

    def _interpolate_step_hour(
        self,
        points: List[Tuple[datetime, float]],
        hour_start: datetime,
        hour_end: datetime,
    ) -> StatisticData | None:
        if not points:
            return None
        start_value = self._step_value_from_points(points, hour_start)
        end_value = self._step_value_from_points(points, hour_end)
        min_value = min(start_value, end_value)
        max_value = max(start_value, end_value)
        return {
            "start": hour_start,
            "mean": start_value,
            "min": min_value,
            "max": max_value,
            "state": end_value,
        }

    def _linear_value_from_points(
        self, points: List[Tuple[datetime, float]], target: datetime
    ) -> float:
        if len(points) == 1:
            return float(points[0][1])
        if target <= points[0][0]:
            start_time, start_value = points[0]
            end_time, end_value = points[1]
        elif target >= points[-1][0]:
            start_time, start_value = points[-2]
            end_time, end_value = points[-1]
        else:
            start_time = points[0][0]
            start_value = points[0][1]
            end_time = points[1][0]
            end_value = points[1][1]
            for index in range(len(points) - 1):
                segment_start, segment_value = points[index]
                segment_end, segment_end_value = points[index + 1]
                if segment_start <= target <= segment_end:
                    start_time = segment_start
                    start_value = segment_value
                    end_time = segment_end
                    end_value = segment_end_value
                    break
        return float(
            self._value_at("linear", start_time, start_value, end_time, end_value, target)
        )

    def _step_value_from_points(
        self, points: List[Tuple[datetime, float]], target: datetime
    ) -> float:
        if target <= points[0][0]:
            return float(points[0][1])
        for index in range(len(points) - 1):
            start_time, start_value = points[index]
            end_time, end_value = points[index + 1]
            if target <= end_time:
                return float(
                    self._value_at("step", start_time, start_value, end_time, end_value, target)
                )
        return float(points[-1][1])

    @staticmethod
    def _history_window(
        entries: List[Dict[str, Any]],
        *,
        key: str = "measured_at",
    ) -> Tuple[datetime | None, datetime | None]:
        timestamps: List[datetime] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            value = entry.get(key)
            if not value:
                continue
            dt_value = dt_util.parse_datetime(value)
            if dt_value is None:
                continue
            timestamps.append(dt_util.as_utc(dt_value))
        if not timestamps:
            return None, None
        timestamps.sort()
        return timestamps[0], timestamps[-1]

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
