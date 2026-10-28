"""Config flow for Mitipi Kevin.

Signing in always goes through **Sign in with Mitipi**: a browser tab with the Mitipi
sign-in page (Google, Apple or e-mail and password). Home Assistant stores the user's
tokens, never a password.

Entries created with e-mail and password by releases before 0.7.0 keep working with their
stored password; when it stops working, re-authentication moves them to Sign in with
Mitipi.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from homeassistant.config_entries import SOURCE_REAUTH, ConfigFlowResult
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import KevinApiClient, KevinAuthError, KevinConnectionError
from .const import (
    AUTH_METHOD_OAUTH,
    CONF_AUTH_METHOD,
    CONF_EMAIL,
    CONF_TOKEN,
    DOMAIN,
    KEVIN_API_BASE_URL,
)
from .oauth import StaticTokenProvider, async_register_implementation, id_token_claims

_LOGGER = logging.getLogger(__name__)


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

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Start Sign in with Mitipi."""
        return await self.async_step_mitipi()

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """Ask the user to sign in again."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Explain why, then open the Mitipi sign-in page."""
        if user_input is None:
            return self.async_show_form(step_id="reauth_confirm")
        return await self.async_step_mitipi()

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
