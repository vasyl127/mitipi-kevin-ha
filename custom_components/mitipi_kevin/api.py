"""Kevin API client (async, in-memory tokens only)."""

from __future__ import annotations

import logging
import re
from typing import Any

import aiohttp
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import HEADER_ID_TOKEN, HEADER_IDEMPOTENCY, MODE_ON, MODE_STAND_BY

_LOGGER = logging.getLogger(__name__)

_IDEMPOTENCY_RE = re.compile(r"^[A-Za-z0-9._-]+$")


class KevinApiError(Exception):
    """Base Kevin API error."""


class KevinAuthError(KevinApiError):
    """Authentication failed."""


class KevinConnectionError(KevinApiError):
    """API unreachable or server error."""


class KevinApiClient:
    """HTTP client for the Mitipi Kevin API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        base_url: str,
        email: str,
        password: str,
    ) -> None:
        self._session = session
        self._base_url = base_url.rstrip("/")
        self._email = email
        self._password = password
        self._access_token: str | None = None
        self._id_token: str | None = None

    @property
    def base_url(self) -> str:
        """Configured API base URL."""
        return self._base_url

    def _url(self, path: str) -> str:
        if not path.startswith("/"):
            path = f"/{path}"
        return f"{self._base_url}{path}"

    def _auth_headers(self) -> dict[str, str]:
        if not self._access_token:
            msg = "Not authenticated"
            raise KevinAuthError(msg)
        headers = {"Authorization": f"Bearer {self._access_token}"}
        if self._id_token:
            headers[HEADER_ID_TOKEN] = self._id_token
        return headers

    async def ensure_authenticated(self) -> None:
        """Log in when no access token is cached."""
        if not self._access_token:
            await self.login()

    async def login(self) -> None:
        """Obtain access and ID tokens."""
        url = self._url("/v1/auth/login")
        try:
            async with self._session.post(
                url,
                json={"email": self._email, "password": self._password},
            ) as resp:
                if resp.status == 401:
                    raise KevinAuthError
                if resp.status >= 500:
                    raise KevinConnectionError
                if resp.status != 200:
                    raise KevinApiError
                data = await resp.json()
        except aiohttp.ClientError as err:
            raise KevinConnectionError from err

        access = data.get("accessToken")
        if not access:
            raise KevinAuthError
        self._access_token = access
        self._id_token = data.get("idToken")

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
        auth: bool = True,
    ) -> tuple[int, Any]:
        """Perform an HTTP request with a single 401 re-login retry."""
        last_status = 0
        last_body: Any = None
        for attempt in range(2):
            if auth and not self._access_token:
                await self.login()
            headers = self._auth_headers() if auth else {}
            if extra_headers:
                headers.update(extra_headers)
            url = self._url(path)
            try:
                async with self._session.request(
                    method, url, json=json, headers=headers
                ) as resp:
                    last_status = resp.status
                    if resp.status == 401 and auth:
                        if attempt == 0:
                            await self.login()
                            continue
                        raise KevinAuthError
                    if resp.content_type == "application/json":
                        last_body = await resp.json()
                    else:
                        last_body = await resp.text()
                    return last_status, last_body
            except aiohttp.ClientError as err:
                raise KevinConnectionError from err
        raise KevinAuthError if last_status == 401 else KevinConnectionError

    async def get_devices(self) -> list[dict[str, Any]]:
        """List devices for the authenticated user."""
        status, data = await self._request("GET", "/v1/devices")
        if status >= 500:
            raise KevinConnectionError
        if status == 401:
            raise KevinAuthError
        if status >= 400:
            raise KevinApiError
        devices = data.get("devices") if isinstance(data, dict) else None
        if not isinstance(devices, list):
            return []
        return devices

    async def get_device_state(self, device_id: str) -> dict[str, Any]:
        """Fetch normalized device state."""
        path = f"/v1/devices/{device_id}/state"
        status, data = await self._request("GET", path)
        if status >= 500:
            raise KevinConnectionError
        if status == 401:
            raise KevinAuthError
        if status >= 400:
            raise KevinApiError
        if not isinstance(data, dict):
            raise KevinApiError
        return data

    async def get_device_capabilities(self, device_id: str) -> dict[str, Any]:
        """Fetch device capabilities."""
        path = f"/v1/devices/{device_id}/capabilities"
        status, data = await self._request("GET", path)
        if status >= 500:
            raise KevinConnectionError
        if status == 401:
            raise KevinAuthError
        if status >= 400:
            raise KevinApiError
        if not isinstance(data, dict):
            raise KevinApiError
        return data

    async def set_mode(self, device_id: str, mode: str, idempotency_key: str) -> None:
        """Request desired mode (202 = accepted, not physical confirmation)."""
        if mode not in (MODE_ON, MODE_STAND_BY):
            msg = "Invalid mode"
            raise KevinApiError(msg)
        if not idempotency_key or len(idempotency_key) > 128:
            msg = "Invalid idempotency key"
            raise KevinApiError(msg)
        if not _IDEMPOTENCY_RE.match(idempotency_key):
            msg = "Invalid idempotency key format"
            raise KevinApiError(msg)

        path = f"/v1/devices/{device_id}/actions/set-mode"
        headers = {HEADER_IDEMPOTENCY: idempotency_key}
        status, _data = await self._request(
            "POST",
            path,
            json={"mode": mode},
            extra_headers=headers,
        )
        if status == 202:
            return
        if status >= 500:
            raise KevinConnectionError
        if status == 401:
            raise KevinAuthError
        if status >= 400:
            raise KevinApiError


def create_client(
    hass: Any,
    base_url: str,
    email: str,
    password: str,
) -> KevinApiClient:
    """Build a client using Home Assistant's shared aiohttp session."""
    session = async_get_clientsession(hass)
    return KevinApiClient(session, base_url, email, password)
