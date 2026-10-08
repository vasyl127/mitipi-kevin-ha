"""Config flow for Mitipi Kevin."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import KevinApiClient, KevinAuthError, KevinConnectionError
from .const import CONF_EMAIL, CONF_PASSWORD, DOMAIN, KEVIN_API_BASE_URL

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class MitipiKevinConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Mitipi Kevin."""

    VERSION = 2

    async def _validate_credentials(
        self,
        email: str,
        password: str,
    ) -> None:
        session = async_get_clientsession(self.hass)
        client = KevinApiClient(session, KEVIN_API_BASE_URL, email, password)
        await client.login()
        await client.get_devices()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            email = user_input[CONF_EMAIL].strip()
            password = user_input[CONF_PASSWORD]
            await self.async_set_unique_id(email.casefold())
            self._abort_if_unique_id_configured()
            try:
                await self._validate_credentials(email, password)
            except KevinAuthError:
                errors["base"] = "invalid_auth"
            except KevinConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error validating Kevin credentials")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=email,
                    data={
                        CONF_EMAIL: email,
                        CONF_PASSWORD: password,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reauth entry point."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm reauth with new credentials."""
        entry = self._get_reauth_entry()

        errors: dict[str, str] = {}
        if user_input is not None:
            email = user_input[CONF_EMAIL].strip()
            password = user_input[CONF_PASSWORD]
            try:
                await self.async_set_unique_id(email.casefold())
                self._abort_if_unique_id_mismatch()
                await self._validate_credentials(email, password)
            except KevinAuthError:
                errors["base"] = "invalid_auth"
            except KevinConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during Kevin reauth")
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={
                        CONF_EMAIL: email,
                        CONF_PASSWORD: password,
                    },
                    reason="reauth_successful",
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_EMAIL, default=entry.data.get(CONF_EMAIL, "")): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )
