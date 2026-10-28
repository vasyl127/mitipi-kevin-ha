"""Sign in with Mitipi: OAuth 2.0 (code + PKCE) against the Kevin API (MA-1023, MA-1024).

The Kevin API hosts the sign-in page (Google, Apple or e-mail and password) and returns
the user's own Auth0 tokens. Home Assistant never sees the password, and the device
routes keep working with ``Authorization: Bearer`` plus ``x-auth0-id-token``.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from typing import Any, cast

from aiohttp import ClientError, ClientResponseError
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_entry_oauth2_flow

from .api import KevinAuthError, KevinConnectionError
from .const import (
    AUTH_METHOD_OAUTH,
    CONF_AUTH_METHOD,
    DOMAIN,
    KEVIN_API_BASE_URL,
    OAUTH_CLIENT_ID,
)

OAUTH_AUTHORIZE_PATH = "/v1/auth/ha/authorize"
OAUTH_TOKEN_PATH = "/v1/auth/ha/token"


def _code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


class MitipiOAuth2Implementation(config_entry_oauth2_flow.LocalOAuth2Implementation):
    """Public client with PKCE (S256); there is no client secret to keep."""

    def __init__(self, hass: HomeAssistant) -> None:
        base = KEVIN_API_BASE_URL.rstrip("/")
        super().__init__(
            hass,
            DOMAIN,
            OAUTH_CLIENT_ID,
            cast(str, None),
            f"{base}{OAUTH_AUTHORIZE_PATH}",
            f"{base}{OAUTH_TOKEN_PATH}",
        )
        # One verifier per config flow; it never leaves this process except to the API.
        self._verifiers: dict[str, str] = {}

    @property
    def name(self) -> str:
        """Name shown if Home Assistant ever lists implementations."""
        return "Mitipi"

    async def async_generate_authorize_url(self, flow_id: str) -> str:
        """Authorize URL with a fresh PKCE challenge for this flow."""
        verifier = secrets.token_urlsafe(64)
        self._verifiers[flow_id] = verifier
        url = await super().async_generate_authorize_url(flow_id)
        separator = "&" if "?" in url else "?"
        return (
            f"{url}{separator}code_challenge={_code_challenge(verifier)}&code_challenge_method=S256"
        )

    async def async_resolve_external_data(self, external_data: Any) -> dict:
        """Exchange the code, sending the verifier of the flow that started it."""
        flow_id = external_data["state"]["flow_id"]
        verifier = self._verifiers.pop(flow_id, "")
        return await self._token_request(
            {
                "grant_type": "authorization_code",
                "code": external_data["code"],
                "redirect_uri": external_data["state"]["redirect_uri"],
                "code_verifier": verifier,
            }
        )


def async_register_implementation(hass: HomeAssistant) -> MitipiOAuth2Implementation:
    """Register (or reuse) the single implementation for this integration."""
    implementations = hass.data.get(config_entry_oauth2_flow.DATA_IMPLEMENTATIONS, {})
    existing = implementations.get(DOMAIN, {}).get(DOMAIN)
    if isinstance(existing, MitipiOAuth2Implementation):
        return existing
    implementation = MitipiOAuth2Implementation(hass)
    config_entry_oauth2_flow.async_register_implementation(hass, DOMAIN, implementation)
    return implementation


def id_token_claims(id_token: str) -> dict[str, Any]:
    """Claims of an ID token the API just handed us over TLS (identity display only)."""
    try:
        payload = id_token.split(".")[1]
        padded = payload + "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(padded))
    except (IndexError, ValueError):
        return {}
    return claims if isinstance(claims, dict) else {}


def is_oauth_entry(entry: ConfigEntry) -> bool:
    """True for entries created with Sign in with Mitipi."""
    return entry.data.get(CONF_AUTH_METHOD) == AUTH_METHOD_OAUTH


class OAuthTokenProvider:
    """Hands the API client fresh Auth0 tokens and maps refresh failures to Kevin errors."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        session: config_entry_oauth2_flow.OAuth2Session,
    ) -> None:
        self._hass = hass
        self._entry = entry
        self._session = session

    async def async_get_tokens(
        self, *, rejected_access_token: str | None = None
    ) -> tuple[str, str]:
        """Return (access_token, id_token), refreshing when expired or just rejected.

        A refresh token rejected by the API (revoked, expired, or the sign-in method was
        switched off) raises ``KevinAuthError`` so Home Assistant starts re-authentication.
        """
        token = self._session.token
        if rejected_access_token and token.get("access_token") == rejected_access_token:
            # Mark only the token that failed as expired; a concurrent request may already
            # have refreshed it, and the session lock serialises the refresh itself.
            self._hass.config_entries.async_update_entry(
                self._entry, data={**self._entry.data, "token": {**token, "expires_at": 0}}
            )
        try:
            await self._session.async_ensure_token_valid()
        except ClientResponseError as err:
            if err.status in (400, 401, 403):
                raise KevinAuthError from err
            raise KevinConnectionError from err
        except (ClientError, TimeoutError) as err:
            raise KevinConnectionError from err
        token = self._session.token
        access_token = token.get("access_token")
        id_token = token.get("id_token")
        if not access_token or not id_token:
            raise KevinAuthError
        return access_token, id_token


class StaticTokenProvider:
    """Tokens just received in the config flow, used once to check the account works."""

    def __init__(self, access_token: str, id_token: str) -> None:
        self._tokens = (access_token, id_token)

    async def async_get_tokens(
        self, *, rejected_access_token: str | None = None
    ) -> tuple[str, str]:
        """Return the fixed tokens; a rejection cannot be fixed by refreshing."""
        if rejected_access_token:
            raise KevinAuthError
        return self._tokens
