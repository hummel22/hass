from __future__ import annotations

from typing import Any, Dict, Optional
from urllib.parse import urlparse

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import aiohttp_client, config_validation as cv

from .api import HASSEMSAuthError, HASSEMSError, HASSEMSClient
from .const import (
    CONF_BASE_URL,
    CONF_GENERATE_TOKEN,
    CONF_INCLUDED_HELPERS,
    CONF_IGNORED_HELPERS,
    CONF_TOKEN,
    DOMAIN,
)
from .coordinator import HASSEMSCoordinator


class HASSEMSFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._reauth_entry: config_entries.ConfigEntry | None = None
        self._discovery_helper: Dict[str, Any] | None = None
        self._discovery_entry: config_entries.ConfigEntry | None = None
        self._generated_token: str | None = None
        self._generated_base_url: str | None = None

    async def async_step_user(self, user_input: Dict[str, Any] | None = None):
        errors: Dict[str, str] = {}
        defaults_base_url = self._generated_base_url
        defaults_token = self._generated_token
        if user_input is not None:
            generate_token = bool(user_input.get(CONF_GENERATE_TOKEN))
            base_url = user_input.get(CONF_BASE_URL)
            provided_token = user_input.get(CONF_TOKEN)
            if generate_token:
                if not base_url:
                    errors[CONF_BASE_URL] = "required"
                else:
                    try:
                        token = await self._async_generate_token(base_url)
                    except (HASSEMSError, HASSEMSAuthError):
                        errors["base"] = "token_generation_failed"
                    else:
                        self._generated_token = token
                        self._generated_base_url = base_url
                        defaults_base_url = base_url
                        defaults_token = token
                        return self.async_show_form(
                            step_id="user",
                            data_schema=self._user_schema(defaults_base_url, defaults_token),
                            errors={"base": "token_generated"},
                        )
            else:
                if base_url:
                    defaults_base_url = base_url
                token_to_use = provided_token or self._generated_token
                if not base_url:
                    errors[CONF_BASE_URL] = "required"
                elif not token_to_use:
                    errors[CONF_TOKEN] = "required"
                else:
                    try:
                        await self._async_validate(
                            {CONF_BASE_URL: base_url, CONF_TOKEN: token_to_use}
                        )
                    except HASSEMSAuthError:
                        errors["base"] = "invalid_auth"
                    except HASSEMSError:
                        errors["base"] = "cannot_connect"
                    else:
                        await self.async_set_unique_id(self._unique_id_from_url(base_url))
                        self._abort_if_unique_id_configured()
                        return self.async_create_entry(
                            title=self._entry_title(base_url),
                            data={
                                CONF_BASE_URL: base_url,
                                CONF_TOKEN: token_to_use,
                            },
                        )
                defaults_token = token_to_use

        schema = self._user_schema(defaults_base_url, defaults_token)
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_reauth(self, entry_data: Dict[str, Any]) -> Dict[str, Any]:
        self._reauth_entry = self._get_entry_for_reauth()
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: Dict[str, Any] | None = None):
        errors: Dict[str, str] = {}
        entry = self._reauth_entry
        if entry is None:
            return self.async_abort(reason="unknown")
        if user_input is not None:
            updated = {CONF_BASE_URL: entry.data[CONF_BASE_URL], CONF_TOKEN: user_input[CONF_TOKEN]}
            try:
                await self._async_validate(updated)
            except HASSEMSAuthError:
                errors["base"] = "invalid_auth"
            except HASSEMSError:
                errors["base"] = "cannot_connect"
            else:
                new_data = {**entry.data, CONF_TOKEN: user_input[CONF_TOKEN]}
                self.hass.config_entries.async_update_entry(entry, data=new_data)
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reauth_successful")
        schema = vol.Schema({vol.Required(CONF_TOKEN): str})
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_integration_discovery(self, discovery_info: Dict[str, Any]):
        helper = discovery_info.get("helper")
        entry_id = self.context.get("entry_id")
        if helper is None or entry_id is None:
            return self.async_abort(reason="unknown")
        entry = self.hass.config_entries.async_get_entry(entry_id)
        if entry is None:
            return self.async_abort(reason="unknown")
        slug = helper.get("slug")
        included = set(entry.options.get(CONF_INCLUDED_HELPERS, []))
        ignored = set(entry.options.get(CONF_IGNORED_HELPERS, []))
        if slug in included or slug in ignored:
            return self.async_abort(reason="already_configured")
        self._discovery_helper = helper
        self._discovery_entry = entry
        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(self, user_input: Dict[str, Any] | None = None):
        errors: Dict[str, str] = {}
        helper = getattr(self, "_discovery_helper", None)
        entry = getattr(self, "_discovery_entry", None)
        if helper is None or entry is None:
            return self.async_abort(reason="unknown")
        slug = helper.get("slug")
        if user_input is not None:
            action = user_input["action"]
            options = dict(entry.options)
            included = set(options.get(CONF_INCLUDED_HELPERS, []))
            ignored = set(options.get(CONF_IGNORED_HELPERS, []))
            if action == "add":
                included.add(slug)
                ignored.discard(slug)
            else:
                ignored.add(slug)
                included.discard(slug)
            options[CONF_INCLUDED_HELPERS] = sorted(included)
            options[CONF_IGNORED_HELPERS] = sorted(ignored)
            self.hass.config_entries.async_update_entry(entry, options=options)
            domain_data = self.hass.data.get(DOMAIN, {})
            entry_data = domain_data.get(entry.entry_id)
            coordinator: HASSEMSCoordinator | None = None
            if entry_data:
                coordinator = entry_data.get("coordinator")
            if coordinator is None:
                return self.async_abort(reason="not_ready")
            coordinator.update_filters(included=included, ignored=ignored)
            coordinator.reapply_filters()
            await coordinator.async_request_refresh()
            return self.async_abort(reason="discovery_processed")
        schema = vol.Schema(
            {
                vol.Required("action", default="add"): vol.In(
                    {
                        "add": "Add to Home Assistant",
                        "ignore": "Ignore",
                    }
                )
            }
        )
        description = {
            "name": helper.get("name", helper.get("slug")),
            "entity_id": helper.get("entity_id"),
        }
        return self.async_show_form(
            step_id="discovery_confirm",
            data_schema=schema,
            description_placeholders=description,
            errors=errors,
        )

    async def _async_validate(self, user_input: Dict[str, Any]) -> None:
        session = aiohttp_client.async_get_clientsession(self.hass)
        client = HASSEMSClient(session, user_input[CONF_BASE_URL], user_input[CONF_TOKEN])
        await client.async_list_helpers()

    async def _async_generate_token(self, base_url: str) -> str:
        session = aiohttp_client.async_get_clientsession(self.hass)
        client = HASSEMSClient(session, base_url, "")
        return await client.async_generate_token()

    def _user_schema(
        self, base_url: Optional[str], token: Optional[str]
    ) -> vol.Schema:
        return vol.Schema(
            {
                vol.Required(CONF_BASE_URL, default=base_url or vol.UNDEFINED): str,
                vol.Optional(CONF_TOKEN, default=token or vol.UNDEFINED): str,
                vol.Optional(CONF_GENERATE_TOKEN, default=False): bool,
            }
        )

    @staticmethod
    def _unique_id_from_url(base_url: str) -> str:
        parsed = urlparse(base_url)
        host = parsed.hostname or base_url
        return host.lower()

    @staticmethod
    def _entry_title(base_url: str) -> str:
        parsed = urlparse(base_url)
        return parsed.hostname or base_url

    def _get_entry_for_reauth(self) -> config_entries.ConfigEntry | None:
        entry_id = self.context.get("entry_id")
        if entry_id:
            return self.hass.config_entries.async_get_entry(entry_id)
        return None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return HASSEMSOptionsFlow(config_entry)


class HASSEMSOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self.config_entry = entry

    async def async_step_init(self, user_input: Dict[str, Any] | None = None):
        domain_data = self.hass.data.get(DOMAIN, {})
        entry_data = domain_data.get(self.config_entry.entry_id)
        coordinator: HASSEMSCoordinator | None = None
        if entry_data:
            coordinator = entry_data.get("coordinator")
        if coordinator is None:
            return self.async_abort(reason="not_ready")
        helpers = coordinator._helpers  # type: ignore[attr-defined]
        helper_options = {
            slug: helper.get("name", slug)
            for slug, helper in sorted(helpers.items(), key=lambda item: item[1].get("name") or item[0])
        }
        if user_input is not None:
            selected = set(user_input[CONF_INCLUDED_HELPERS])
            existing_ignored = set(self.config_entry.options.get(CONF_IGNORED_HELPERS, []))
            ignored = (set(helper_options) - selected) | (existing_ignored - set(helper_options))
            return self.async_create_entry(
                title="Options",
                data={
                    CONF_INCLUDED_HELPERS: sorted(selected),
                    CONF_IGNORED_HELPERS: sorted(ignored),
                },
            )
        default_included = self.config_entry.options.get(CONF_INCLUDED_HELPERS, list(helper_options))
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_INCLUDED_HELPERS,
                    default=default_included,
                ): cv.multi_select(helper_options)
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
