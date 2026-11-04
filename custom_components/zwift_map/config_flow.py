"""Config flow: Zwift account credentials."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ZwiftAuthError, ZwiftClient, ZwiftError
from .const import CONF_PLAYER_ID, DOMAIN

_LOGGER = logging.getLogger(__name__)

SCHEMA = vol.Schema({vol.Required(CONF_USERNAME): str, vol.Required(CONF_PASSWORD): str})


class ZwiftMapConfigFlow(ConfigFlow, domain=DOMAIN):
    """Ask for the Zwift account and check it against the profile endpoint."""

    VERSION = 1

    async def _async_validate(self, data: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, str]]:
        client = ZwiftClient(
            async_get_clientsession(self.hass), data[CONF_USERNAME], data[CONF_PASSWORD]
        )
        try:
            profile = await client.async_get_profile()
        except ZwiftAuthError:
            return None, {"base": "invalid_auth"}
        except (ZwiftError, TimeoutError, OSError):
            _LOGGER.exception("Could not reach Zwift")
            return None, {"base": "cannot_connect"}
        if "id" not in profile:
            return None, {"base": "cannot_connect"}
        return profile, {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            profile, errors = await self._async_validate(user_input)
            if profile:
                await self.async_set_unique_id(str(profile["id"]))
                self._abort_if_unique_id_configured()
                name = " ".join(
                    p for p in (profile.get("firstName"), profile.get("lastName")) if p
                ) or user_input[CONF_USERNAME]
                return self.async_create_entry(
                    title=f"Zwift Map – {name}",
                    data={**user_input, CONF_PLAYER_ID: int(profile["id"])},
                )
        return self.async_show_form(step_id="user", data_schema=SCHEMA, errors=errors)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            profile, errors = await self._async_validate(user_input)
            if profile:
                await self.async_set_unique_id(str(profile["id"]))
                self._abort_if_unique_id_mismatch(reason="wrong_account")
                return self.async_update_reload_and_abort(
                    entry, data_updates={**user_input, CONF_PLAYER_ID: int(profile["id"])}
                )
        schema = self.add_suggested_values_to_schema(
            SCHEMA, {CONF_USERNAME: entry.data.get(CONF_USERNAME)}
        )
        return self.async_show_form(step_id="reauth_confirm", data_schema=schema, errors=errors)
