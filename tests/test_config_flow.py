"""Config flow tests for entries created with e-mail and password before 0.7.0.

New entries and re-authentication use Sign in with Mitipi (tests/test_sign_in_with_mitipi.py);
there is no e-mail and password form any more.
"""

from __future__ import annotations

from aioresponses import aioresponses
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mitipi_kevin.const import CONF_BASE_URL, CONF_EMAIL, CONF_PASSWORD, DOMAIN
from tests.conftest import (
    TEST_BASE_URL,
    TEST_EMAIL,
    TEST_PASSWORD,
    KevinApiStub,
)


async def test_setup_never_shows_a_password_form(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] != FlowResultType.FORM
    assert "password" not in str(result.get("data_schema"))


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


async def test_a_rejected_password_starts_reauth_through_the_mitipi_page(
    hass: HomeAssistant,
    kevin_stub: KevinApiStub,
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=2,
        unique_id=TEST_EMAIL.casefold(),
        data={CONF_EMAIL: TEST_EMAIL, CONF_PASSWORD: TEST_PASSWORD},
    )
    entry.add_to_hass(hass)
    kevin_stub.login_status = 401
    with aioresponses() as mock:
        kevin_stub.apply(mock)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert [f["context"]["source"] for f in flows] == [config_entries.SOURCE_REAUTH]
    assert flows[0]["step_id"] == "reauth_confirm"
