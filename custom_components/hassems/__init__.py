from __future__ import annotations

import logging
from typing import Any, Dict

from aiohttp import ClientSession
from homeassistant.components import webhook
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_TOKEN, __version__ as HA_VERSION
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client

from .api import HASSEMSError, HASSEMSClient
from .const import (
    CONF_BASE_URL,
    CONF_INCLUDED_ENTITIES,
    CONF_IGNORED_ENTITIES,
    CONF_SUBSCRIPTION_ID,
    CONF_WEBHOOK_ID,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import HASSEMSCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: Dict[str, Any]) -> bool:
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})

    session: ClientSession = aiohttp_client.async_get_clientsession(hass)
    client = HASSEMSClient(session, entry.data[CONF_BASE_URL], entry.data[CONF_TOKEN])
    coordinator = HASSEMSCoordinator(hass, client, entry)
    await coordinator.async_config_entry_first_refresh()

    options = dict(entry.options)
    included = set(options.get(CONF_INCLUDED_ENTITIES, []))
    ignored = set(options.get(CONF_IGNORED_ENTITIES, []))
    if not options.get(CONF_INCLUDED_ENTITIES):
        included = set(coordinator._entities.keys()) - ignored  # type: ignore[attr-defined]
        options[CONF_INCLUDED_ENTITIES] = sorted(included)
        options[CONF_IGNORED_ENTITIES] = sorted(ignored)
        hass.config_entries.async_update_entry(entry, options=options)
    coordinator.update_filters(included=included, ignored=ignored)
    coordinator.reapply_filters()

    webhook_id = entry.data.get(CONF_WEBHOOK_ID)
    if not webhook_id:
        webhook_id = webhook.async_generate_id()
        new_data = {**entry.data, CONF_WEBHOOK_ID: webhook_id}
        hass.config_entries.async_update_entry(entry, data=new_data)
    webhook.async_register(hass, DOMAIN, "HASSEMS", webhook_id, coordinator.async_handle_webhook)
    webhook_url = webhook.async_generate_url(hass, webhook_id)

    try:
        subscription = await client.async_register_webhook(
            webhook_url,
            description=entry.entry_id,
            metadata={"entry_id": entry.entry_id},
        )
        coordinator.set_subscription(subscription)
        if coordinator.subscription_id is not None:
            updated_data = {**entry.data, CONF_SUBSCRIPTION_ID: coordinator.subscription_id}
            hass.config_entries.async_update_entry(entry, data=updated_data)
    except HASSEMSSError as err:
        _LOGGER.warning("Unable to register HASSEMS webhook: %s", err)

    await _async_sync_connection(hass, entry, client, coordinator)

    def _schedule_connection_sync() -> None:
        hass.async_create_task(_async_sync_connection(hass, entry, client, coordinator))

    unsubscribe_sync = coordinator.async_add_listener(_schedule_connection_sync)

    hass.data[DOMAIN][entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
        "webhook_id": webhook_id,
        "sync_unsub": unsubscribe_sync,
    }

    entry.async_on_unload(
        entry.add_update_listener(_async_update_listener)
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    data = hass.data[DOMAIN].pop(entry.entry_id, None)
    if data is None:
        return unload_ok

    webhook_id = data.get("webhook_id")
    if webhook_id:
        webhook.async_unregister(hass, webhook_id)

    sync_unsub = data.get("sync_unsub")
    if callable(sync_unsub):
        sync_unsub()

    client: HASSEMSClient = data["client"]
    coordinator: HASSEMSCoordinator = data["coordinator"]
    subscription_id = coordinator.subscription_id or entry.data.get(CONF_SUBSCRIPTION_ID)
    if subscription_id is not None:
        try:
            await client.async_delete_webhook(subscription_id)
        except HASSEMSSError as err:
            _LOGGER.debug("Failed to delete HASSEMS webhook %s: %s", subscription_id, err)

    try:
        await client.async_delete_connection(entry.entry_id)
    except HASSEMSError as err:
        _LOGGER.debug("Failed to delete HASSEMS integration connection %s: %s", entry.entry_id, err)

    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    coordinator: HASSEMSCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    await coordinator.async_update_options(entry)
    client: HASSEMSClient = hass.data[DOMAIN][entry.entry_id]["client"]
    await _async_sync_connection(hass, entry, client, coordinator)


def _build_connection_payload(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: HASSEMSCoordinator,
) -> Dict[str, Any]:
    options = entry.options or {}
    included = sorted(options.get(CONF_INCLUDED_ENTITIES, []))
    ignored = sorted(options.get(CONF_IGNORED_ENTITIES, []))
    unit_system = getattr(getattr(hass.config, "units", None), "name", None)
    metadata: Dict[str, Any] = {
        "base_url": entry.data.get(CONF_BASE_URL),
        "webhook_id": entry.data.get(CONF_WEBHOOK_ID),
        "subscription_id": coordinator.subscription_id
        or entry.data.get(CONF_SUBSCRIPTION_ID),
        "home_assistant": {
            "name": hass.config.location_name,
            "time_zone": getattr(hass.config, "time_zone", None),
            "unit_system": unit_system,
            "version": HA_VERSION,
        },
    }
    metadata["home_assistant"] = {
        key: value
        for key, value in metadata["home_assistant"].items()
        if value not in (None, "")
    }
    if not metadata["home_assistant"]:
        metadata.pop("home_assistant")
    metadata = {
        key: value
        for key, value in metadata.items()
        if value not in (None, "", {}, [])
    }
    payload: Dict[str, Any] = {
        "entry_id": entry.entry_id,
        "title": entry.title,
        "included_entities": included,
        "ignored_entities": ignored,
        "entity_count": len(coordinator.data or {}),
    }
    if metadata:
        payload["metadata"] = metadata
    return payload


async def _async_sync_connection(
    hass: HomeAssistant,
    entry: ConfigEntry,
    client: HASSEMSClient,
    coordinator: HASSEMSCoordinator,
) -> None:
    payload = _build_connection_payload(hass, entry, coordinator)
    try:
        await client.async_upsert_connection(payload)
    except HASSEMSError as err:
        _LOGGER.debug("Unable to sync HASSEMS connection %s: %s", entry.entry_id, err)
