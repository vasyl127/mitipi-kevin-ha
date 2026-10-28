"""Config flow for Mitipi Kevin.

Two ways to sign in, offered as the Kevin API allows them (admin console, MA-1020):

- **Sign in with Mitipi**: a browser tab with the Mitipi sign-in page (Google, Apple or
  e-mail and password). Home Assistant stores the user's tokens, never a password.
- **Email and password**: the original form; the password is kept in the entry.

Re-authentication offers the same choice and updates the existing entry.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import SOURCE_REAUTH, ConfigFlowResult
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import KevinApiClient, KevinAuthError, KevinConnectionError, SignInMethods
from .const import (
    AUTH_METHOD_OAUTH,
    CONF_AUTH_METHOD,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_TOKEN,
    DOMAIN,
    KEVIN_API_BASE_URL,
)
from .oauth import StaticTokenProvider, async_register_implementation, id_token_claims

_LOGGER = logging.getLogger(__name__)

STEP_PASSWORD_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
    }
)

MENU_MITIPI = "mitipi"
MENU_PASSWORD = "password"


class MitipiKevinConfigFlow(config_entry_oauth2_flow.AbstractOAuth2FlowHandler, domain=DOMAIN):
    """Handle a config flow for Mitipi Kevin."""

    DOMAIN = DOMAIN
    VERSION = 2

    @property
    def logger(self) -> logging.Logger:
        """Logger used by the OAuth2 base flow."""
        return _LOGGER

    def _client(self, **kwargs: Any) -> KevinApiClient:
        return KevinApiClient(async_get_clientsession(self.hass), KEVIN_API_BASE_URL, **kwargs)

    async def _sign_in_methods(self) -> SignInMethods:
        try:
            return await self._client().get_sign_in_methods()
        except KevinConnectionError:
            # Offline or an older API: the password form reports the real error.
            return SignInMethods.password_only()

    async def _method_menu(self, step_id: str) -> ConfigFlowResult:
        methods = await self._sign_in_methods()
        options = []
        if methods.mitipi_sign_in:
            options.append(MENU_MITIPI)
        if methods.email_password:
            options.append(MENU_PASSWORD)
        if not options:
            return self.async_abort(reason="no_sign_in_method")
        if len(options) == 1:
            if options[0] == MENU_MITIPI:
                return await self.async_step_mitipi()
            return await self.async_step_password()
        return self.async_show_menu(step_id=step_id, menu_options=options)

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Choose how to sign in."""
        return await self._method_menu("user")

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """Start re-authentication with the same choice as setup."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose how to sign in again."""
        return await self._method_menu("reauth_confirm")

    # ----- Sign in with Mitipi -------------------------------------------------------

    async def async_step_mitipi(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Open the Mitipi sign-in page in a browser tab."""
        if "my" not in self.hass.config.components:
            # The Kevin API only returns to My Home Assistant (exact redirect allow-list).
            return self.async_abort(reason="my_home_assistant_required")
        self.flow_impl = async_register_implementation(self.hass)
        return await self.async_step_auth()

    async def async_oauth_create_entry(self, data: dict[str, Any]) -> ConfigFlowResult:
        """Create or update the entry once the Kevin API returned the tokens."""
        token = data[CONF_TOKEN]
        claims = id_token_claims(token.get("id_token", ""))
        email = claims.get("email") if isinstance(claims.get("email"), str) else None
        subject = claims.get("sub") if isinstance(claims.get("sub"), str) else None
        if not email and not subject:
            return self.async_abort(reason="oauth_error")

        try:
            provider = StaticTokenProvider(token["access_token"], token["id_token"])
            await self._client(token_provider=provider).get_devices()
        except KevinAuthError:
            return self.async_abort(reason="oauth_unauthorized")
        except KevinConnectionError:
            return self.async_abort(reason="cannot_connect")
        except Exception:
            _LOGGER.exception("Unexpected error checking the Kevin account after sign-in")
            return self.async_abort(reason="unknown")

        entry_data = {**data, CONF_AUTH_METHOD: AUTH_METHOD_OAUTH}
        if email:
            entry_data[CONF_EMAIL] = email
        await self.async_set_unique_id((email or subject or "").casefold())
        if self.source == SOURCE_REAUTH:
            self._abort_if_unique_id_mismatch(reason="wrong_account")
            return self.async_update_reload_and_abort(
                self._get_reauth_entry(), data=entry_data, reason="reauth_successful"
            )
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=email or "Mitipi account", data=entry_data)

    # ----- E-mail and password -----------------------------------------------------

    async def _validate_credentials(self, email: str, password: str) -> None:
        client = self._client(email=email, password=password)
        await client.login()
        await client.get_devices()

    async def async_step_password(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """E-mail and password form (setup and re-authentication)."""
        reauth = self.source == SOURCE_REAUTH
        errors: dict[str, str] = {}
        if user_input is not None:
            email = user_input[CONF_EMAIL].strip()
            password = user_input[CONF_PASSWORD]
            await self.async_set_unique_id(email.casefold())
            if reauth:
                self._abort_if_unique_id_mismatch(reason="wrong_account")
            else:
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
                data = {CONF_EMAIL: email, CONF_PASSWORD: password}
                if reauth:
                    # `data=` replaces everything, so a former token entry loses its tokens.
                    return self.async_update_reload_and_abort(
                        self._get_reauth_entry(), data=data, reason="reauth_successful"
                    )
                return self.async_create_entry(title=email, data=data)

        suggested: dict[str, Any] = {}
        if reauth and (email := self._get_reauth_entry().data.get(CONF_EMAIL)):
            suggested[CONF_EMAIL] = email
        return self.async_show_form(
            step_id="password",
            data_schema=self.add_suggested_values_to_schema(STEP_PASSWORD_SCHEMA, suggested),
            errors=errors,
        )
