"""Config flow tests."""

from __future__ import annotations

import pytest
from aioresponses import aioresponses
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
                CONF_BASE_URL: TEST_BASE_URL,
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
                CONF_BASE_URL: TEST_BASE_URL,
                CONF_EMAIL: TEST_EMAIL,
                CONF_PASSWORD: TEST_PASSWORD,
            },
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == TEST_EMAIL
    assert result["data"][CONF_BASE_URL] == TEST_BASE_URL
    assert result["data"][CONF_EMAIL] == TEST_EMAIL
    assert result["data"][CONF_PASSWORD] == TEST_PASSWORD
    assert "access-token" not in str(result["data"])
    assert_allowed_kevin_paths(kevin_stub.requested_paths)

    # Duplicate account aborts
    with aioresponses() as mock:
        kevin_stub.apply(mock)
        duplicate = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={
                CONF_BASE_URL: TEST_BASE_URL,
                CONF_EMAIL: TEST_EMAIL,
                CONF_PASSWORD: TEST_PASSWORD,
            },
        )
    assert duplicate["type"] == FlowResultType.ABORT
    assert duplicate["reason"] == "already_configured"


async def test_reconfigure_updates_existing_entry_without_creating_another(
    hass: HomeAssistant,
) -> None:
    """A base URL change validates and updates the linked config entry only."""
    reconfigured_url = "https://kevin-reconfigured.test/api"
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=TEST_EMAIL.casefold(),
        data={
            CONF_BASE_URL: TEST_BASE_URL,
            CONF_EMAIL: TEST_EMAIL,
            CONF_PASSWORD: TEST_PASSWORD,
        },
    )
    entry.add_to_hass(hass)
    stub = KevinApiStub(reconfigured_url)
    stub.set_devices([])

    with aioresponses() as mock:
        stub.apply(mock)
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": config_entries.SOURCE_RECONFIGURE,
                "entry_id": entry.entry_id,
            },
            data={CONF_BASE_URL: reconfigured_url},
        )
        await hass.async_block_till_done()

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_BASE_URL] == reconfigured_url
    assert entry.data[CONF_EMAIL] == TEST_EMAIL
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1
    assert_allowed_kevin_paths(stub.requested_paths)
