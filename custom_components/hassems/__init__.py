from __future__ import annotations

import logging
from typing import Any, Dict

from aiohttp import ClientSession
from homeassistant.components import webhook
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client

from .api import HASSEMSError, HASSEMSClient
from .const import (
    CONF_BASE_URL,
    CONF_INCLUDED_HELPERS,
    CONF_IGNORED_HELPERS,
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
    included = set(options.get(CONF_INCLUDED_HELPERS, []))
    ignored = set(options.get(CONF_IGNORED_HELPERS, []))
    if not options.get(CONF_INCLUDED_HELPERS):
        included = set(coordinator._helpers.keys()) - ignored  # type: ignore[attr-defined]
        options[CONF_INCLUDED_HELPERS] = sorted(included)
        options[CONF_IGNORED_HELPERS] = sorted(ignored)
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

    hass.data[DOMAIN][entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
        "webhook_id": webhook_id,
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

    client: HASSEMSClient = data["client"]
    coordinator: HASSEMSCoordinator = data["coordinator"]
    subscription_id = coordinator.subscription_id or entry.data.get(CONF_SUBSCRIPTION_ID)
    if subscription_id is not None:
        try:
            await client.async_delete_webhook(subscription_id)
        except HASSEMSSError as err:
            _LOGGER.debug("Failed to delete HASSEMS webhook %s: %s", subscription_id, err)

    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    coordinator: HASSEMSCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    await coordinator.async_update_options(entry)
