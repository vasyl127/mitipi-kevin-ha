"""Shared pytest fixtures."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

import pytest
from aioresponses import CallbackResult, aioresponses

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(scope="session", autouse=True)
def prime_aiohttp_resolver_thread() -> None:
    """Start aiohttp/pycares shutdown thread once so HA verify_cleanup stays stable."""
    import asyncio

    import aiohttp

    async def _prime() -> None:
        try:
            async with aiohttp.ClientSession() as session:
                await session.get(
                    "http://127.0.0.1:9",
                    timeout=aiohttp.ClientTimeout(total=0.2),
                )
        except Exception:
            pass

    asyncio.run(_prime())


@pytest.fixture(autouse=True)
def enable_mitipi_integration(enable_custom_integrations: None) -> None:
    """Load custom_components/mitipi_kevin for each test."""


@pytest.fixture(autouse=True)
def patch_kevin_api_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the integration at the test Kevin API host."""
    import custom_components.mitipi_kevin.api as api_mod
    import custom_components.mitipi_kevin.config_flow as flow_mod
    import custom_components.mitipi_kevin.const as const_mod

    monkeypatch.setattr(const_mod, "KEVIN_API_BASE_URL", TEST_BASE_URL)
    monkeypatch.setattr(flow_mod, "KEVIN_API_BASE_URL", TEST_BASE_URL)
    monkeypatch.setattr(api_mod, "KEVIN_API_BASE_URL", TEST_BASE_URL)


TEST_BASE_URL = "https://kevin.test/api"
TEST_EMAIL = "user@example.com"
TEST_PASSWORD = "secret-password"

DEVICE_ONE = {
    "id": "11111111-1111-1111-1111-111111111111",
    "kevinDeviceId": "K-DEVICEONE",
    "name": "Living room",
}
DEVICE_TWO = {
    "id": "22222222-2222-2222-2222-222222222222",
    "kevinDeviceId": "K-DEVICETWO",
    "name": "Bedroom",
}

ALLOWED_PATH_PATTERNS = (
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


def assert_allowed_kevin_paths(requested_paths: list[str]) -> None:
    """Fail when a recorded request path is outside the Kevin API surface."""
    for path in requested_paths:
        if not any(pattern.match(path) for pattern in ALLOWED_PATH_PATTERNS):
            msg = f"Disallowed API path requested: {path}"
            raise AssertionError(msg)


def summary_payload(
    device: dict[str, Any],
    *,
    availability: str = "online",
    mode: str = "ON",
    firmware_version: str = "1.88",
    subscription: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "device": device,
        "availability": availability,
        "mode": mode,
        "firmwareVersion": firmware_version,
        "subscription": subscription
        or {"status": "unknown", "source": "not_configured"},
        "scenes": [],
    }


def scenes_payload(
    *,
    scenes: list[dict[str, Any]] | None = None,
    active_scene_ids: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "scenes": scenes
        or [
            {
                "id": "scene-home-1",
                "title": "Cozy evening",
                "description": "Warm lights",
                "environment": "HOME",
            },
        ],
        "activeSceneIds": active_scene_ids if active_scene_ids is not None else [],
    }


class KevinApiStub:
    """Register Kevin API responses and record requested paths."""

    def __init__(self, base_url: str = TEST_BASE_URL) -> None:
        self.base_url = base_url.rstrip("/")
        self.requested_paths: list[str] = []
        self.devices: list[dict[str, Any]] = []
        self.summaries: dict[str, dict[str, Any]] = {}
        self.scenes: dict[str, dict[str, Any]] = {}
        self.login_count = 0
        self.login_requests: list[dict[str, Any]] = []
        self._devices_401_once = False
        self._set_mode_calls: list[dict[str, Any]] = []
        self._apply_scene_calls: list[dict[str, Any]] = []
        self._reboot_calls: list[dict[str, Any]] = []

    def set_devices(self, devices: list[dict[str, Any]]) -> None:
        self.devices = devices
        for device in devices:
            device_id = device["id"]
            self.summaries.setdefault(
                device_id,
                summary_payload(device),
            )
            self.scenes.setdefault(device_id, scenes_payload())

    def enable_single_devices_401_retry(self) -> None:
        """First authenticated devices list returns 401 (exercises re-login)."""
        self._devices_401_once = True

    def _record(self, url: str | object) -> None:
        path = urlparse(str(url)).path
        prefix = urlparse(self.base_url).path.rstrip("/")
        if prefix and path.startswith(prefix):
            path = path[len(prefix) :] or "/"
        self.requested_paths.append(path)

    def apply(self, mock: aioresponses) -> None:
        """Register handlers on aioresponses."""

        def login_handler(url: str, **kwargs) -> CallbackResult:
            self._record(url)
            self.login_count += 1
            self.login_requests.append(
                {
                    "url": str(url),
                    "json": kwargs.get("json"),
                }
            )
            return CallbackResult(
                status=200,
                payload={
                    "accessToken": "access-token",
                    "idToken": "id-token",
                    "tokenType": "Bearer",
                    "expiresIn": 3600,
                },
            )

        mock.post(f"{self.base_url}/v1/auth/login", callback=login_handler, repeat=True)

        def devices_handler(url: str, **kwargs) -> CallbackResult:
            self._record(url)
            if self._devices_401_once:
                self._devices_401_once = False
                return CallbackResult(status=401)
            return CallbackResult(status=200, payload={"devices": self.devices})

        mock.get(f"{self.base_url}/v1/devices", callback=devices_handler, repeat=True)

        def summary_handler(url: str, **kwargs) -> CallbackResult:
            self._record(url)
            device_id = str(url).rsplit("/", 2)[-2]
            return CallbackResult(
                status=200,
                payload=self.summaries.get(
                    device_id,
                    summary_payload({"id": device_id}, availability="unknown"),
                ),
            )

        mock.get(
            re.compile(rf"{re.escape(self.base_url)}/v1/devices/[^/]+/summary"),
            callback=summary_handler,
            repeat=True,
        )

        def scenes_handler(url: str, **kwargs) -> CallbackResult:
            self._record(url)
            device_id = str(url).rsplit("/", 2)[-2]
            return CallbackResult(
                status=200,
                payload=self.scenes.get(device_id, scenes_payload()),
            )

        mock.get(
            re.compile(rf"{re.escape(self.base_url)}/v1/devices/[^/]+/scenes"),
            callback=scenes_handler,
            repeat=True,
        )

        def set_mode_handler(url: str, **kwargs) -> CallbackResult:
            self._record(url)
            headers = kwargs.get("headers") or {}
            idem = headers.get("Idempotency-Key") or headers.get("idempotency-key")
            self._set_mode_calls.append(
                {
                    "url": str(url),
                    "json": kwargs.get("json"),
                    "idempotency_key": idem,
                }
            )
            return CallbackResult(status=202, payload={"accepted": True})

        mock.post(
            re.compile(rf"{re.escape(self.base_url)}/v1/devices/[^/]+/actions/set-mode"),
            callback=set_mode_handler,
            repeat=True,
        )

        def apply_scene_handler(url: str, **kwargs) -> CallbackResult:
            self._record(url)
            headers = kwargs.get("headers") or {}
            self._apply_scene_calls.append(
                {
                    "json": kwargs.get("json"),
                    "idempotency_key": headers.get("Idempotency-Key"),
                }
            )
            return CallbackResult(status=202, payload={"accepted": True})

        mock.post(
            re.compile(rf"{re.escape(self.base_url)}/v1/devices/[^/]+/actions/apply-scene"),
            callback=apply_scene_handler,
            repeat=True,
        )

        def reboot_handler(url: str, **kwargs) -> CallbackResult:
            self._record(url)
            headers = kwargs.get("headers") or {}
            self._reboot_calls.append({"idempotency_key": headers.get("Idempotency-Key")})
            return CallbackResult(status=202, payload={"accepted": True})

        mock.post(
            re.compile(rf"{re.escape(self.base_url)}/v1/devices/[^/]+/actions/reboot"),
            callback=reboot_handler,
            repeat=True,
        )


@pytest.fixture
def kevin_stub() -> KevinApiStub:
    """Fresh Kevin API stub."""
    return KevinApiStub()


@pytest.fixture
def mock_kevin_api(kevin_stub: KevinApiStub) -> Callable[[], aioresponses]:
    """Context manager factory wrapping aioresponses."""

    def _factory() -> aioresponses:
        mock = aioresponses()
        kevin_stub.apply(mock)
        return mock

    return _factory
