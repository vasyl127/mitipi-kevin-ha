"""Download diagnostics: useful for support, free of credentials and personal data (MA-937)."""

from __future__ import annotations

import json

from aioresponses import aioresponses
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mitipi_kevin.const import (
    CONF_EMAIL,
    CONF_PASSWORD,
    DOMAIN,
    INTEGRATION_VERSION,
)
from custom_components.mitipi_kevin.diagnostics import async_get_config_entry_diagnostics
from custom_components.mitipi_kevin.environment import ENVIRONMENT
from tests.conftest import (
    DEVICE_ONE,
    DEVICE_TWO,
    TEST_EMAIL,
    TEST_PASSWORD,
    KevinApiStub,
)


async def _setup(hass: HomeAssistant, kevin_stub: KevinApiStub) -> MockConfigEntry:
    kevin_stub.set_devices([DEVICE_ONE, DEVICE_TWO])
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=TEST_EMAIL,
        version=2,
        data={CONF_EMAIL: TEST_EMAIL, CONF_PASSWORD: TEST_PASSWORD},
        unique_id=TEST_EMAIL.casefold(),
    )
    entry.add_to_hass(hass)
    with aioresponses() as mock:
        kevin_stub.apply(mock)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


async def test_diagnostics_describe_the_integration_and_each_device(
    hass: HomeAssistant, kevin_stub: KevinApiStub
) -> None:
    entry = await _setup(hass, kevin_stub)

    diag = await async_get_config_entry_diagnostics(hass, entry)

    assert diag["integration"]["version"] == INTEGRATION_VERSION
    assert diag["integration"]["environment"] == ENVIRONMENT
    assert diag["coordinator"]["last_update_success"] is True
    assert diag["coordinator"]["failed_polls_in_a_row"] == 0
    assert diag["coordinator"]["preferences_state"] == "configured"
    devices = {d["api_device_id"]: d for d in diag["devices"]}
    assert set(devices) == {DEVICE_ONE["id"], DEVICE_TWO["id"]}
    assert devices[DEVICE_ONE["id"]]["mode"] == "ON"
    assert devices[DEVICE_ONE["id"]]["summary_available"] is True
    # Serialisable as-is: Home Assistant writes the result straight to JSON.
    json.dumps(diag)


async def test_diagnostics_never_contain_credentials_or_personal_data(
    hass: HomeAssistant, kevin_stub: KevinApiStub
) -> None:
    entry = await _setup(hass, kevin_stub)

    dumped = json.dumps(await async_get_config_entry_diagnostics(hass, entry))

    for secret in (
        TEST_EMAIL,
        TEST_EMAIL.casefold(),
        TEST_PASSWORD,
        "access-token",
        "id-token",
        DEVICE_ONE["name"],
        DEVICE_TWO["name"],
    ):
        assert secret not in dumped, secret
    assert "**REDACTED**" in dumped


async def test_diagnostics_for_an_entry_that_failed_to_load(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_EMAIL: TEST_EMAIL, CONF_PASSWORD: TEST_PASSWORD},
    )
    entry.add_to_hass(hass)
    entry.runtime_data = None

    diag = await async_get_config_entry_diagnostics(hass, entry)

    assert diag["coordinator"] is None
    assert TEST_PASSWORD not in json.dumps(diag)


async def test_diagnostics_download_through_home_assistant(
    hass: HomeAssistant, hass_client, kevin_stub: KevinApiStub
) -> None:
    """The platform is found by Home Assistant's own Download diagnostics endpoint."""
    from homeassistant.setup import async_setup_component

    entry = await _setup(hass, kevin_stub)
    assert await async_setup_component(hass, "diagnostics", {})
    client = await hass_client()

    response = await client.get(f"/api/diagnostics/config_entry/{entry.entry_id}")

    assert response.status == 200
    body = await response.json()
    assert body["data"]["integration"]["version"] == INTEGRATION_VERSION
    assert TEST_PASSWORD not in json.dumps(body)
