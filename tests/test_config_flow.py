"""Config flow tests."""

from __future__ import annotations

import pytest
from aioresponses import CallbackResult, aioresponses
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mitipi_kevin.const import CONF_BASE_URL, CONF_EMAIL, CONF_PASSWORD, DOMAIN
from tests.conftest import (
    TEST_BASE_URL,
    TEST_EMAIL,
    TEST_PASSWORD,
    KevinApiStub,
    assert_allowed_kevin_paths,
)


@pytest.mark.parametrize(
    "status",
    [401],
)
async def test_config_flow_invalid_credentials_translated(
    hass: HomeAssistant,
    kevin_stub: KevinApiStub,
    status: int,
) -> None:
    """Invalid credentials show translated auth error without API body leakage."""
    with aioresponses() as mock:
        mock.post(
            f"{TEST_BASE_URL}/v1/auth/login",
            status=status,
            payload={"error": "invalid_credentials", "detail": "secret server detail"},
        )
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={
                CONF_EMAIL: TEST_EMAIL,
                CONF_PASSWORD: TEST_PASSWORD,
            },
        )
        await hass.async_block_till_done()

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}
    assert "secret server detail" not in str(result)
    assert_allowed_kevin_paths(["/v1/auth/login"])


async def test_config_flow_happy_path(hass: HomeAssistant, kevin_stub: KevinApiStub) -> None:
    """Valid credentials create a unique config entry via Kevin API validation."""
    kevin_stub.set_devices([])
    with aioresponses() as mock:
        kevin_stub.apply(mock)
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={
                CONF_EMAIL: TEST_EMAIL,
                CONF_PASSWORD: TEST_PASSWORD,
            },
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == TEST_EMAIL
    assert CONF_BASE_URL not in result["data"]
    assert result["data"][CONF_EMAIL] == TEST_EMAIL
    assert result["data"][CONF_PASSWORD] == TEST_PASSWORD
    assert "access-token" not in str(result["data"])
    assert_allowed_kevin_paths(kevin_stub.requested_paths)
    assert kevin_stub.login_requests[0]["url"] == f"{TEST_BASE_URL}/v1/auth/login"

    # Duplicate account aborts
    with aioresponses() as mock:
        kevin_stub.apply(mock)
        duplicate = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={
                CONF_EMAIL: TEST_EMAIL,
                CONF_PASSWORD: TEST_PASSWORD,
            },
        )
    assert duplicate["type"] == FlowResultType.ABORT
    assert duplicate["reason"] == "already_configured"


async def test_config_flow_ignores_injected_base_url(
    hass: HomeAssistant,
    kevin_stub: KevinApiStub,
) -> None:
    """Extra base_url input cannot redirect credentials to another host."""
    evil_base = "https://evil-attacker.example/api"
    kevin_stub.set_devices([])

    def evil_login(url: str, **kwargs) -> CallbackResult:
        msg = "Credentials must not be sent to attacker host"
        raise AssertionError(msg)

    with aioresponses() as mock:
        mock.post(f"{evil_base}/v1/auth/login", callback=evil_login, repeat=True)
        kevin_stub.apply(mock)
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={
                CONF_EMAIL: TEST_EMAIL,
                CONF_PASSWORD: TEST_PASSWORD,
                CONF_BASE_URL: evil_base,
            },
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert all(str(req["url"]).startswith(TEST_BASE_URL) for req in kevin_stub.login_requests)


async def test_legacy_entry_migration_drops_base_url(
    hass: HomeAssistant,
    kevin_stub: KevinApiStub,
) -> None:
    """Version 1 entries lose stored base_url and use the fixed Kevin API host."""
    legacy_url = "https://legacy-override.example/api"
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=1,
        unique_id=TEST_EMAIL.casefold(),
        data={
            CONF_BASE_URL: legacy_url,
            CONF_EMAIL: TEST_EMAIL,
            CONF_PASSWORD: TEST_PASSWORD,
        },
    )
    entry.add_to_hass(hass)
    kevin_stub.set_devices([])

    with aioresponses() as mock:
        kevin_stub.apply(mock)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.version == 2
    assert CONF_BASE_URL not in entry.data
    assert all(str(req["url"]).startswith(TEST_BASE_URL) for req in kevin_stub.login_requests)


async def test_reauth_updates_credentials_without_duplicate_entry(
    hass: HomeAssistant,
    kevin_stub: KevinApiStub,
) -> None:
    """Expired credentials can be renewed on the existing config entry."""
    new_password = "new-secret-password"
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=TEST_EMAIL.casefold(),
        data={
            CONF_EMAIL: TEST_EMAIL,
            CONF_PASSWORD: TEST_PASSWORD,
        },
    )
    entry.add_to_hass(hass)
    kevin_stub.set_devices([])

    with aioresponses() as mock:
        kevin_stub.apply(mock)
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": config_entries.SOURCE_REAUTH,
                "entry_id": entry.entry_id,
            },
        )
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "reauth_confirm"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_EMAIL: TEST_EMAIL,
                CONF_PASSWORD: new_password,
            },
        )
        await hass.async_block_till_done()

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_PASSWORD] == new_password
    assert entry.data[CONF_EMAIL] == TEST_EMAIL
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1
    assert_allowed_kevin_paths(kevin_stub.requested_paths)
    login_body = kevin_stub.login_requests[-1]["json"]
    assert login_body["email"] == TEST_EMAIL
    assert login_body["password"] == new_password
    assert kevin_stub.login_requests[-1]["url"] == f"{TEST_BASE_URL}/v1/auth/login"
