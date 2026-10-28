"""Sign in with Mitipi: menu, OAuth (code + PKCE), token refresh and re-auth (MA-1023..1025)."""

from __future__ import annotations

import base64
import hashlib
import json
import time
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest
from aioresponses import CallbackResult, aioresponses
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.config_entry_oauth2_flow import MY_AUTH_CALLBACK_PATH
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mitipi_kevin.const import (
    AUTH_METHOD_OAUTH,
    CONF_AUTH_METHOD,
    CONF_EMAIL,
    CONF_PASSWORD,
    DOMAIN,
    OAUTH_CLIENT_ID,
)
from custom_components.mitipi_kevin.diagnostics import async_get_config_entry_diagnostics
from tests.conftest import (
    DEVICE_ONE,
    TEST_BASE_URL,
    TEST_EMAIL,
    TEST_PASSWORD,
    KevinApiStub,
    assert_allowed_kevin_paths,
)

TOKEN_URL = f"{TEST_BASE_URL}/v1/auth/ha/token"
BOTH = {
    "emailPassword": {"enabled": True},
    "mitipiSignIn": {"enabled": True, "providers": ["google", "apple", "password"]},
}
MITIPI_ONLY = {
    "emailPassword": {"enabled": False},
    "mitipiSignIn": {"enabled": True, "providers": ["google"]},
}


def id_token(email: str | None = TEST_EMAIL, sub: str = "auth0|user-1") -> str:
    claims: dict[str, Any] = {"sub": sub}
    if email:
        claims["email"] = email
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    return f"header.{payload}.signature"


def token_response(
    access: str = "oauth-access-1",
    refresh: str | None = "oauth-refresh-1",
    email: str | None = TEST_EMAIL,
    expires_in: int = 86400,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "access_token": access,
        "id_token": id_token(email),
        "token_type": "Bearer",
        "expires_in": expires_in,
    }
    if refresh:
        body["refresh_token"] = refresh
    return body


@pytest.fixture
def with_my(hass: HomeAssistant) -> None:
    """My Home Assistant is part of default_config; the redirect allow-list needs it."""
    hass.config.components.add("my")


async def _external_step(hass: HomeAssistant, entry=None, result=None):
    if result is None and entry is not None:
        result = await entry.start_reauth_flow(hass)
    elif result is None:
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
    if result["type"] == FlowResultType.MENU:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"next_step_id": "mitipi"}
        )
    assert result["type"] == FlowResultType.EXTERNAL_STEP, result
    return result


async def _finish_oauth(
    hass: HomeAssistant, mock: aioresponses, result: dict, token_body: dict[str, Any]
) -> tuple[dict, dict[str, list[str]]]:
    """Play the browser's part: return with a code, then let the flow exchange it."""
    url = urlparse(result["url"])
    query = parse_qs(url.query)
    sent: dict[str, list[str]] = {}

    def token_handler(_url: str, **kwargs) -> CallbackResult:
        sent.update({k: [v] for k, v in kwargs["data"].items()})
        return CallbackResult(status=200, payload=token_body)

    mock.post(TOKEN_URL, callback=token_handler)
    flow_id = result["flow_id"]
    redirect_uri = query["redirect_uri"][0]
    done = await hass.config_entries.flow.async_configure(
        flow_id, {"code": "kevin-code", "state": {"flow_id": flow_id, "redirect_uri": redirect_uri}}
    )
    assert done["type"] == FlowResultType.EXTERNAL_STEP_DONE
    final = await hass.config_entries.flow.async_configure(flow_id)
    await hass.async_block_till_done()
    return final, {**{k: v for k, v in query.items()}, **{f"token_{k}": v for k, v in sent.items()}}


async def test_menu_offers_both_methods_when_the_api_allows_them(
    hass: HomeAssistant, kevin_stub: KevinApiStub
) -> None:
    kevin_stub.sign_in_methods = BOTH
    with aioresponses() as mock:
        kevin_stub.apply(mock)
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] == FlowResultType.MENU
        assert result["step_id"] == "user"
        assert result["menu_options"] == ["mitipi", "password"]

        password = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"next_step_id": "password"}
        )
    assert password["type"] == FlowResultType.FORM
    assert password["step_id"] == "password"


async def test_no_method_and_missing_my_home_assistant_abort_with_a_reason(
    hass: HomeAssistant, kevin_stub: KevinApiStub
) -> None:
    kevin_stub.sign_in_methods = {
        "emailPassword": {"enabled": False},
        "mitipiSignIn": {"enabled": False, "providers": []},
    }
    with aioresponses() as mock:
        kevin_stub.apply(mock)
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
    assert result == {**result, "type": FlowResultType.ABORT, "reason": "no_sign_in_method"}

    kevin_stub.sign_in_methods = MITIPI_ONLY
    with aioresponses() as mock:
        kevin_stub.apply(mock)
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "my_home_assistant_required"


async def test_an_older_api_without_methods_keeps_the_password_form(
    hass: HomeAssistant, kevin_stub: KevinApiStub
) -> None:
    kevin_stub.sign_in_methods = None
    with aioresponses() as mock:
        kevin_stub.apply(mock)
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "password"


async def test_sign_in_with_mitipi_creates_a_token_entry(
    hass: HomeAssistant, kevin_stub: KevinApiStub, with_my: None
) -> None:
    kevin_stub.sign_in_methods = MITIPI_ONLY
    kevin_stub.set_devices([DEVICE_ONE])
    with aioresponses() as mock:
        kevin_stub.apply(mock)
        result = await _external_step(hass)

        authorize = urlparse(result["url"])
        assert f"{authorize.scheme}://{authorize.netloc}{authorize.path}" == (
            f"{TEST_BASE_URL}/v1/auth/ha/authorize"
        )
        result, sent = await _finish_oauth(hass, mock, result, token_response())

    assert sent["client_id"] == [OAUTH_CLIENT_ID]
    assert sent["response_type"] == ["code"]
    assert sent["redirect_uri"] == [MY_AUTH_CALLBACK_PATH]
    assert sent["code_challenge_method"] == ["S256"]
    verifier = sent["token_code_verifier"][0]
    digest = hashlib.sha256(verifier.encode()).digest()
    assert sent["code_challenge"] == [base64.urlsafe_b64encode(digest).rstrip(b"=").decode()]
    assert sent["token_grant_type"] == ["authorization_code"]
    assert sent["token_code"] == ["kevin-code"]
    assert "token_client_secret" not in sent, "public client: no secret is sent"

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == TEST_EMAIL
    data = result["data"]
    assert data[CONF_AUTH_METHOD] == AUTH_METHOD_OAUTH
    assert data[CONF_EMAIL] == TEST_EMAIL
    assert CONF_PASSWORD not in data
    assert data["token"]["refresh_token"] == "oauth-refresh-1"
    assert result["result"].unique_id == TEST_EMAIL.casefold()
    # The account was checked with the new tokens before the entry was created.
    assert kevin_stub.devices_auth_headers[0] == {
        "authorization": "Bearer oauth-access-1",
        "id_token": id_token(),
    }
    assert kevin_stub.login_count == 0, "no password login for a token entry"
    assert_allowed_kevin_paths(kevin_stub.requested_paths)


async def test_the_same_account_cannot_be_added_twice_across_methods(
    hass: HomeAssistant, kevin_stub: KevinApiStub, with_my: None
) -> None:
    MockConfigEntry(
        domain=DOMAIN,
        unique_id=TEST_EMAIL.casefold(),
        data={CONF_EMAIL: TEST_EMAIL, CONF_PASSWORD: TEST_PASSWORD},
    ).add_to_hass(hass)
    kevin_stub.sign_in_methods = MITIPI_ONLY
    kevin_stub.set_devices([])
    with aioresponses() as mock:
        kevin_stub.apply(mock)
        result = await _external_step(hass)
        result, _ = await _finish_oauth(
            hass, mock, result, token_response(email=TEST_EMAIL.upper())
        )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_rejected_tokens_abort_instead_of_creating_a_broken_entry(
    hass: HomeAssistant, kevin_stub: KevinApiStub, with_my: None
) -> None:
    kevin_stub.sign_in_methods = MITIPI_ONLY
    kevin_stub.rejected_access_tokens = {"oauth-access-1"}
    with aioresponses() as mock:
        kevin_stub.apply(mock)
        result = await _external_step(hass)
        result, _ = await _finish_oauth(hass, mock, result, token_response())
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "oauth_unauthorized"
    assert hass.config_entries.async_entries(DOMAIN) == []


def _oauth_entry(expires_at: float, **token: Any) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        version=2,
        title=TEST_EMAIL,
        unique_id=TEST_EMAIL.casefold(),
        data={
            "auth_implementation": DOMAIN,
            CONF_AUTH_METHOD: AUTH_METHOD_OAUTH,
            CONF_EMAIL: TEST_EMAIL,
            "token": {
                **token_response(),
                "expires_at": expires_at,
                **token,
            },
        },
    )


async def test_token_entry_refreshes_before_expiry_and_stores_the_rotated_token(
    hass: HomeAssistant, kevin_stub: KevinApiStub
) -> None:
    entry = _oauth_entry(time.time() - 10)
    entry.add_to_hass(hass)
    kevin_stub.set_devices([DEVICE_ONE])
    refreshes: list[dict[str, str]] = []

    def refresh_handler(_url: str, **kwargs) -> CallbackResult:
        refreshes.append(dict(kwargs["data"]))
        return CallbackResult(
            status=200, payload=token_response(access="oauth-access-2", refresh="oauth-refresh-2")
        )

    with aioresponses() as mock:
        kevin_stub.apply(mock)
        mock.post(TOKEN_URL, callback=refresh_handler, repeat=True)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert len(refreshes) == 1, "parallel requests share one refresh"
    assert refreshes[0]["grant_type"] == "refresh_token"
    assert refreshes[0]["refresh_token"] == "oauth-refresh-1"
    assert refreshes[0]["client_id"] == OAUTH_CLIENT_ID
    assert entry.data["token"]["refresh_token"] == "oauth-refresh-2"
    assert entry.data["token"]["expires_at"] > time.time()
    assert {h["authorization"] for h in kevin_stub.devices_auth_headers} == {
        "Bearer oauth-access-2"
    }
    assert kevin_stub.login_count == 0


async def test_a_401_refreshes_once_and_retries(
    hass: HomeAssistant, kevin_stub: KevinApiStub
) -> None:
    entry = _oauth_entry(time.time() + 3600)
    entry.add_to_hass(hass)
    kevin_stub.set_devices([DEVICE_ONE])
    kevin_stub.rejected_access_tokens = {"oauth-access-1"}

    with aioresponses() as mock:
        kevin_stub.apply(mock)
        mock.post(
            TOKEN_URL,
            payload=token_response(access="oauth-access-2", refresh=None),
            repeat=True,
        )
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert kevin_stub.devices_auth_headers[-1]["authorization"] == "Bearer oauth-access-2"
    # Auth0 did not rotate: the stored refresh token is kept, not blanked.
    assert entry.data["token"]["refresh_token"] == "oauth-refresh-1"


@pytest.mark.parametrize("status", [400, 401])
async def test_a_revoked_refresh_token_starts_reauth(
    hass: HomeAssistant, kevin_stub: KevinApiStub, status: int
) -> None:
    entry = _oauth_entry(time.time() - 10)
    entry.add_to_hass(hass)
    kevin_stub.set_devices([DEVICE_ONE])
    with aioresponses() as mock:
        kevin_stub.apply(mock)
        mock.post(TOKEN_URL, status=status, payload={"error": "invalid_grant"}, repeat=True)
        assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert [f["context"]["source"] for f in flows] == [config_entries.SOURCE_REAUTH]


async def test_an_unreachable_token_endpoint_retries_later(
    hass: HomeAssistant, kevin_stub: KevinApiStub
) -> None:
    entry = _oauth_entry(time.time() - 10)
    entry.add_to_hass(hass)
    with aioresponses() as mock:
        kevin_stub.apply(mock)
        mock.post(TOKEN_URL, status=503, payload={"error": "temporarily_unavailable"}, repeat=True)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert hass.config_entries.flow.async_progress() == []


async def test_password_entry_reauths_when_an_admin_switches_password_sign_in_off(
    hass: HomeAssistant, kevin_stub: KevinApiStub
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=TEST_EMAIL.casefold(),
        data={CONF_EMAIL: TEST_EMAIL, CONF_PASSWORD: TEST_PASSWORD},
    )
    entry.add_to_hass(hass)
    kevin_stub.login_status = 403
    with aioresponses() as mock:
        kevin_stub.apply(mock)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert [f["context"]["source"] for f in hass.config_entries.flow.async_progress()] == [
        config_entries.SOURCE_REAUTH
    ]


async def test_reauth_switches_a_password_entry_to_sign_in_with_mitipi(
    hass: HomeAssistant, kevin_stub: KevinApiStub, with_my: None
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=2,
        unique_id=TEST_EMAIL.casefold(),
        data={CONF_EMAIL: TEST_EMAIL, CONF_PASSWORD: TEST_PASSWORD},
    )
    entry.add_to_hass(hass)
    kevin_stub.sign_in_methods = BOTH
    kevin_stub.set_devices([])
    with aioresponses() as mock:
        kevin_stub.apply(mock)
        menu = await entry.start_reauth_flow(hass)
        assert menu["type"] == FlowResultType.MENU
        assert menu["step_id"] == "reauth_confirm"
        result = await _external_step(hass, result=menu)
        result, _ = await _finish_oauth(hass, mock, result, token_response())

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_AUTH_METHOD] == AUTH_METHOD_OAUTH
    assert CONF_PASSWORD not in entry.data, "the stored password is dropped"
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


async def test_reauth_with_another_mitipi_account_is_refused(
    hass: HomeAssistant, kevin_stub: KevinApiStub, with_my: None
) -> None:
    entry = _oauth_entry(time.time() + 3600)
    entry.add_to_hass(hass)
    kevin_stub.sign_in_methods = MITIPI_ONLY
    kevin_stub.set_devices([])
    with aioresponses() as mock:
        kevin_stub.apply(mock)
        result = await _external_step(hass, entry=entry)
        result, _ = await _finish_oauth(
            hass, mock, result, token_response(access="other", email="someone@else.example")
        )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "wrong_account"
    assert entry.data["token"]["access_token"] == "oauth-access-1"


async def test_diagnostics_redact_the_tokens(hass: HomeAssistant, kevin_stub: KevinApiStub) -> None:
    entry = _oauth_entry(time.time() + 3600)
    entry.add_to_hass(hass)
    kevin_stub.set_devices([DEVICE_ONE])
    with aioresponses() as mock:
        kevin_stub.apply(mock)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    diag = await async_get_config_entry_diagnostics(hass, entry)
    dumped = json.dumps(diag)
    for secret in ("oauth-access-1", "oauth-refresh-1", id_token(), TEST_EMAIL):
        assert secret not in dumped
    assert diag["integration"]["sign_in_method"] == "mitipi"
    assert diag["entry"]["data"]["token"] == "**REDACTED**"
