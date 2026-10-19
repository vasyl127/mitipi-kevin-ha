"""Kevin API client unit tests."""

from __future__ import annotations

import re
import uuid

import pytest
from aioresponses import CallbackResult, aioresponses
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.mitipi_kevin.api import KevinApiClient, KevinApiError, KevinAuthError
from custom_components.mitipi_kevin.const import (
    HEADER_CLIENT,
    HEADER_ID_TOKEN,
    HEADER_IDEMPOTENCY,
    INTEGRATION_VERSION,
    MODE_ON,
)
from tests.conftest import TEST_BASE_URL, TEST_EMAIL, TEST_PASSWORD


async def test_authenticated_requests_send_bearer_and_id_token(
    hass,
) -> None:
    """Device calls include Authorization and x-auth0-id-token headers."""
    captured: list[dict[str, str]] = []

    def devices_handler(url: str, **kwargs) -> CallbackResult:
        headers = kwargs.get("headers") or {}
        captured.append(dict(headers))
        return CallbackResult(status=200, payload={"devices": []})

    with aioresponses() as mock:
        mock.post(
            f"{TEST_BASE_URL}/v1/auth/login",
            status=200,
            payload={
                "accessToken": "access-token",
                "idToken": "id-token",
            },
        )
        mock.get(f"{TEST_BASE_URL}/v1/devices", callback=devices_handler, repeat=True)
        session = async_get_clientsession(hass)
        client = KevinApiClient(session, TEST_BASE_URL, TEST_EMAIL, TEST_PASSWORD)
        await client.login()
        await client.get_devices()

    assert len(captured) == 1
    headers = captured[0]
    assert headers["Authorization"] == "Bearer access-token"
    assert headers[HEADER_ID_TOKEN] == "id-token"
    assert headers[HEADER_CLIENT] == f"mitipi_kevin/{INTEGRATION_VERSION}"


async def test_login_names_the_integration_release(hass) -> None:
    """The API records which integration release is calling (admin panel shows it)."""
    captured: list[dict[str, str]] = []

    def login_handler(url: str, **kwargs) -> CallbackResult:
        captured.append(dict(kwargs.get("headers") or {}))
        return CallbackResult(status=200, payload={"accessToken": "a", "idToken": "i"})

    with aioresponses() as mock:
        mock.post(f"{TEST_BASE_URL}/v1/auth/login", callback=login_handler)
        session = async_get_clientsession(hass)
        client = KevinApiClient(session, TEST_BASE_URL, TEST_EMAIL, TEST_PASSWORD)
        await client.login()

    assert captured[0][HEADER_CLIENT] == f"mitipi_kevin/{INTEGRATION_VERSION}"
    # Must match the API parser: /^mitipi_kevin\/(\S+)$/ with a short version token.
    assert re.fullmatch(r"mitipi_kevin/[0-9A-Za-z][0-9A-Za-z.+-]{0,31}", captured[0][HEADER_CLIENT])


def test_manifest_and_const_versions_match() -> None:
    """The header reports INTEGRATION_VERSION, so it must equal the released manifest version."""
    import json
    from pathlib import Path

    manifest = json.loads(
        (Path(__file__).parents[1] / "custom_components/mitipi_kevin/manifest.json").read_text()
    )
    assert manifest["version"] == INTEGRATION_VERSION


async def test_login_without_id_token_fails(hass) -> None:
    """Login responses must include both access and ID tokens."""
    with aioresponses() as mock:
        mock.post(
            f"{TEST_BASE_URL}/v1/auth/login",
            status=200,
            payload={"accessToken": "access-token"},
        )
        session = async_get_clientsession(hass)
        client = KevinApiClient(session, TEST_BASE_URL, TEST_EMAIL, TEST_PASSWORD)
        with pytest.raises(KevinAuthError):
            await client.login()


async def test_disallowed_api_path_rejected(hass) -> None:
    """Client refuses paths outside the Kevin API surface."""
    session = async_get_clientsession(hass)
    client = KevinApiClient(session, TEST_BASE_URL, TEST_EMAIL, TEST_PASSWORD)
    with pytest.raises(KevinApiError):
        await client._request("GET", "/v1/legacy/devices", auth=False)


async def test_client_rejects_non_approved_base_url(hass) -> None:
    """Only the fixed Kevin API base URL is permitted."""
    session = async_get_clientsession(hass)
    with pytest.raises(KevinApiError):
        KevinApiClient(session, "https://evil.example/api", TEST_EMAIL, TEST_PASSWORD)


async def test_get_devices_401_triggers_exactly_one_relogin(hass) -> None:
    """A single 401 on devices causes one re-login attempt, then success."""
    login_count = 0
    devices_calls = 0

    def login_handler(url: str, **kwargs) -> CallbackResult:
        nonlocal login_count
        login_count += 1
        return CallbackResult(
            status=200,
            payload={"accessToken": f"access-{login_count}", "idToken": f"id-{login_count}"},
        )

    def devices_handler(url: str, **kwargs) -> CallbackResult:
        nonlocal devices_calls
        devices_calls += 1
        if devices_calls == 1:
            return CallbackResult(status=401)
        return CallbackResult(status=200, payload={"devices": []})

    with aioresponses() as mock:
        mock.post(f"{TEST_BASE_URL}/v1/auth/login", callback=login_handler, repeat=True)
        mock.get(f"{TEST_BASE_URL}/v1/devices", callback=devices_handler, repeat=True)
        session = async_get_clientsession(hass)
        client = KevinApiClient(session, TEST_BASE_URL, TEST_EMAIL, TEST_PASSWORD)
        await client.login()
        devices = await client.get_devices()

    assert devices == []
    assert login_count == 2
    assert devices_calls == 2


async def test_set_mode_payload_idempotency_and_refresh_not_optimistic(hass) -> None:
    """set-mode uses JSON payload, fresh idempotency key, and does not mutate local tokens."""
    device_id = "11111111-1111-1111-1111-111111111111"
    set_mode_calls: list[dict] = []
    state_modes = ["STAND_BY"]

    def state_handler(url: str, **kwargs) -> CallbackResult:
        return CallbackResult(
            status=200,
            payload={"availability": "online", "reported": {"mode": state_modes[0]}},
        )

    with aioresponses() as mock:
        mock.post(
            f"{TEST_BASE_URL}/v1/auth/login",
            status=200,
            payload={"accessToken": "access-token", "idToken": "id-token"},
        )
        mock.get(
            f"{TEST_BASE_URL}/v1/devices/{device_id}/state",
            callback=state_handler,
            repeat=True,
        )

        def set_mode_handler(url: str, **kwargs) -> CallbackResult:
            headers = kwargs.get("headers") or {}
            set_mode_calls.append(
                {
                    "json": kwargs.get("json"),
                    "idempotency_key": headers.get(HEADER_IDEMPOTENCY),
                }
            )
            return CallbackResult(status=202, payload={"accepted": True})

        mock.post(
            f"{TEST_BASE_URL}/v1/devices/{device_id}/actions/set-mode",
            callback=set_mode_handler,
            repeat=True,
        )
        session = async_get_clientsession(hass)
        client = KevinApiClient(session, TEST_BASE_URL, TEST_EMAIL, TEST_PASSWORD)
        await client.login()
        idem = uuid.uuid4().hex
        await client.set_mode(device_id, MODE_ON, idem)
        state = await client.get_device_state(device_id)

    assert len(set_mode_calls) == 1
    call = set_mode_calls[0]
    assert call["json"] == {"mode": MODE_ON}
    assert call["idempotency_key"] == idem
    assert re.match(r"^[A-Za-z0-9._-]+$", call["idempotency_key"])
    assert state["reported"]["mode"] == "STAND_BY"


async def test_apply_scene_and_reboot_mutations(hass) -> None:
    """apply-scene and reboot accept 202 with idempotency keys."""
    device_id = "11111111-1111-1111-1111-111111111111"
    calls: list[str] = []

    def capture_action(url: str, **kwargs) -> CallbackResult:
        headers = kwargs.get("headers") or {}
        calls.append(headers.get(HEADER_IDEMPOTENCY))
        return CallbackResult(status=202, payload={"accepted": True})

    with aioresponses() as mock:
        mock.post(
            f"{TEST_BASE_URL}/v1/auth/login",
            status=200,
            payload={"accessToken": "access-token", "idToken": "id-token"},
        )
        mock.post(
            re.compile(rf"{re.escape(TEST_BASE_URL)}/v1/devices/{device_id}/actions/.*"),
            callback=capture_action,
            repeat=True,
        )
        session = async_get_clientsession(hass)
        client = KevinApiClient(session, TEST_BASE_URL, TEST_EMAIL, TEST_PASSWORD)
        await client.login()
        await client.apply_scene(device_id, "scene-1", "key-apply-scene")
        await client.reboot_device(device_id, "key-reboot")

    assert calls == ["key-apply-scene", "key-reboot"]
