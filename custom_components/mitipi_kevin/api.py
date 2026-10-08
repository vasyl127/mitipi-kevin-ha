"""Kevin API client (async, in-memory tokens only)."""

from __future__ import annotations

import logging
import re
from typing import Any

import aiohttp
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    HEADER_ID_TOKEN,
    HEADER_IDEMPOTENCY,
    KEVIN_API_BASE_URL,
    MODE_ON,
    MODE_STAND_BY,
)

_LOGGER = logging.getLogger(__name__)

_IDEMPOTENCY_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_ALLOWED_PATH_PATTERNS = (
    re.compile(r"^/v1/auth/login$"),
    re.compile(r"^/v1/devices$"),
    re.compile(r"^/v1/devices/[^/]+/state$"),
    re.compile(r"^/v1/devices/[^/]+/capabilities$"),
    re.compile(r"^/v1/devices/[^/]+/summary$"),
    re.compile(r"^/v1/devices/[^/]+/scenes$"),
    re.compile(r"^/v1/devices/[^/]+/subscription$"),
    re.compile(r"^/v1/devices/[^/]+/actions/set-mode$"),
    re.compile(r"^/v1/devices/[^/]+/actions/apply-scene$"),
    re.compile(r"^/v1/devices/[^/]+/actions/clear-scenes$"),
    re.compile(r"^/v1/devices/[^/]+/actions/reboot$"),
)


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
        normalized = base_url.rstrip("/")
        if normalized != KEVIN_API_BASE_URL.rstrip("/"):
            msg = "Disallowed API base URL"
            raise KevinApiError(msg)
        self._base_url = normalized
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
        self._ensure_allowed_path(path)
        return f"{self._base_url}{path}"

    @staticmethod
    def _ensure_allowed_path(path: str) -> None:
        if not any(pattern.match(path) for pattern in _ALLOWED_PATH_PATTERNS):
            msg = "Disallowed API path"
            raise KevinApiError(msg)

    def _auth_headers(self) -> dict[str, str]:
        if not self._access_token or not self._id_token:
            msg = "Not authenticated"
            raise KevinAuthError(msg)
        return {
            "Authorization": f"Bearer {self._access_token}",
            HEADER_ID_TOKEN: self._id_token,
        }

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
        id_token = data.get("idToken")
        if not access or not id_token:
            raise KevinAuthError
        self._access_token = access
        self._id_token = id_token

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

    @staticmethod
    def _validate_idempotency_key(idempotency_key: str) -> None:
        if not idempotency_key or len(idempotency_key) > 128:
            msg = "Invalid idempotency key"
            raise KevinApiError(msg)
        if not _IDEMPOTENCY_RE.match(idempotency_key):
            msg = "Invalid idempotency key format"
            raise KevinApiError(msg)

    def _raise_for_mutation_status(self, status: int) -> None:
        if status == 202:
            return
        if status >= 500:
            raise KevinConnectionError
        if status == 401:
            raise KevinAuthError
        if status >= 400:
            raise KevinApiError

    async def _post_device_action(
        self,
        device_id: str,
        action: str,
        body: dict[str, Any],
        idempotency_key: str,
    ) -> None:
        self._validate_idempotency_key(idempotency_key)
        path = f"/v1/devices/{device_id}/actions/{action}"
        headers = {HEADER_IDEMPOTENCY: idempotency_key}
        status, _data = await self._request(
            "POST",
            path,
            json=body,
            extra_headers=headers,
        )
        self._raise_for_mutation_status(status)

    async def _get_device_json(self, path: str) -> dict[str, Any]:
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

    async def get_device_summary(self, device_id: str) -> dict[str, Any]:
        """Fetch consolidated device card summary."""
        return await self._get_device_json(f"/v1/devices/{device_id}/summary")

    async def get_device_scenes(self, device_id: str) -> dict[str, Any]:
        """Fetch scene catalog and active scene ids."""
        return await self._get_device_json(f"/v1/devices/{device_id}/scenes")

    async def get_device_subscription(self, device_id: str) -> dict[str, Any]:
        """Fetch subscription details."""
        return await self._get_device_json(f"/v1/devices/{device_id}/subscription")

    async def set_mode(self, device_id: str, mode: str, idempotency_key: str) -> None:
        """Request desired mode (202 = accepted, not physical confirmation)."""
        if mode not in (MODE_ON, MODE_STAND_BY):
            msg = "Invalid mode"
            raise KevinApiError(msg)
        await self._post_device_action(
            device_id, "set-mode", {"mode": mode}, idempotency_key
        )

    async def apply_scene(
        self,
        device_id: str,
        scene_id: str,
        idempotency_key: str,
        *,
        score: float | None = None,
    ) -> None:
        """Apply a scene without changing power mode."""
        body: dict[str, Any] = {"sceneId": scene_id}
        if score is not None:
            body["score"] = score
        await self._post_device_action(device_id, "apply-scene", body, idempotency_key)

    async def clear_scenes(self, device_id: str, idempotency_key: str) -> None:
        """Clear active scenes."""
        await self._post_device_action(device_id, "clear-scenes", {}, idempotency_key)

    async def reboot_device(self, device_id: str, idempotency_key: str) -> None:
        """Request device reboot."""
        await self._post_device_action(device_id, "reboot", {}, idempotency_key)


def create_client(
    hass: Any,
    email: str,
    password: str,
) -> KevinApiClient:
    """Build a client using Home Assistant's shared aiohttp session."""
    session = async_get_clientsession(hass)
    return KevinApiClient(session, KEVIN_API_BASE_URL, email, password)
