"""Integration setup, coordinator, entities, and API behavior."""

from __future__ import annotations

import re

import pytest
from aioresponses import CallbackResult, aioresponses
from homeassistant.components import switch
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mitipi_kevin.api import KevinApiClient, KevinAuthError
from custom_components.mitipi_kevin.const import CONF_EMAIL, CONF_PASSWORD, DOMAIN
from tests.conftest import (
    DEVICE_ONE,
    DEVICE_TWO,
    TEST_BASE_URL,
    TEST_EMAIL,
    TEST_PASSWORD,
    KevinApiStub,
    assert_allowed_kevin_paths,
    state_payload,
)


async def _setup_entry(hass: HomeAssistant, kevin_stub: KevinApiStub) -> MockConfigEntry:
    kevin_stub.set_devices([DEVICE_ONE, DEVICE_TWO])
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_EMAIL: TEST_EMAIL,
            CONF_PASSWORD: TEST_PASSWORD,
        },
        unique_id=TEST_EMAIL.casefold(),
    )
    entry.add_to_hass(hass)
    with aioresponses() as mock:
        kevin_stub.apply(mock)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


async def test_coordinator_two_devices_unique_entities(
    hass: HomeAssistant, kevin_stub: KevinApiStub
) -> None:
    """Two devices yield unique entity ids and device identifiers."""
    entry = await _setup_entry(hass, kevin_stub)
    registry = er.async_get(hass)
    entities = er.async_entries_for_config_entry(registry, entry.entry_id)
    assert len(entities) == 6
    unique_ids = {entity.unique_id for entity in entities}
    assert len(unique_ids) == 6
    for device in (DEVICE_ONE, DEVICE_TWO):
        device_entities = [
            e for e in entities if e.unique_id.startswith(f"{device['id']}_")
        ]
        assert len(device_entities) == 3
    assert_allowed_kevin_paths(kevin_stub.requested_paths)


async def test_zero_devices_succeeds_without_entities(
    hass: HomeAssistant, kevin_stub: KevinApiStub
) -> None:
    """Empty device list completes setup without entities."""
    kevin_stub.set_devices([])
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_EMAIL: TEST_EMAIL,
            CONF_PASSWORD: TEST_PASSWORD,
        },
    )
    entry.add_to_hass(hass)
    with aioresponses() as mock:
        kevin_stub.apply(mock)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    registry = er.async_get(hass)
    assert er.async_entries_for_config_entry(registry, entry.entry_id) == []
    assert_allowed_kevin_paths(kevin_stub.requested_paths)


async def test_state_mapping_online_mode_and_unknown_unavailable(
    hass: HomeAssistant, kevin_stub: KevinApiStub
) -> None:
    """Online + ON maps correctly; unknown availability stays unavailable."""
    kevin_stub.set_devices([DEVICE_ONE])
    kevin_stub.states[DEVICE_ONE["id"]] = state_payload(availability="online", mode="ON")
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_EMAIL: TEST_EMAIL,
            CONF_PASSWORD: TEST_PASSWORD,
        },
    )
    entry.add_to_hass(hass)
    with aioresponses() as mock:
        kevin_stub.apply(mock)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    registry = er.async_get(hass)
    mode_entity = registry.async_get_entity_id(
        "sensor", DOMAIN, f"{DEVICE_ONE['id']}_mode"
    )
    connectivity_entity = registry.async_get_entity_id(
        "binary_sensor", DOMAIN, f"{DEVICE_ONE['id']}_connectivity"
    )
    assert hass.states.get(mode_entity).state == "ON"
    assert hass.states.get(connectivity_entity).state == "on"

    kevin_stub.states[DEVICE_ONE["id"]] = state_payload(availability="unknown", mode="ON")
    coordinator = entry.runtime_data
    with aioresponses() as mock:
        kevin_stub.apply(mock)
        await coordinator.async_refresh()
        await hass.async_block_till_done()

    assert hass.states.get(mode_entity).state == "unavailable"
    assert hass.states.get(connectivity_entity).state == "unavailable"


async def test_switch_set_mode_idempotency_and_no_optimistic_state(
    hass: HomeAssistant, kevin_stub: KevinApiStub
) -> None:
    """Switch sends set-mode with idempotency key; 202 does not change reported mode."""
    kevin_stub.set_devices([DEVICE_ONE])
    kevin_stub.states[DEVICE_ONE["id"]] = state_payload(mode="STAND_BY")
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_EMAIL: TEST_EMAIL,
            CONF_PASSWORD: TEST_PASSWORD,
        },
    )
    entry.add_to_hass(hass)
    with aioresponses() as mock:
        kevin_stub.apply(mock)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    registry = er.async_get(hass)
    switch_entity = registry.async_get_entity_id(
        "switch", DOMAIN, f"{DEVICE_ONE['id']}_power"
    )
    assert hass.states.get(switch_entity).state == "off"

    with aioresponses() as mock:
        kevin_stub.apply(mock)
        await hass.services.async_call(
            switch.DOMAIN,
            "turn_on",
            {"entity_id": switch_entity},
            blocking=True,
        )
        await hass.async_block_till_done()

    assert len(kevin_stub._set_mode_calls) == 1
    call = kevin_stub._set_mode_calls[0]
    assert call["json"] == {"mode": "ON"}
    assert call["idempotency_key"]
    assert re.match(r"^[A-Za-z0-9._-]+$", call["idempotency_key"])
    assert hass.states.get(switch_entity).state == "off"

    with aioresponses() as mock:
        kevin_stub.apply(mock)
        await hass.services.async_call(
            switch.DOMAIN,
            "turn_off",
            {"entity_id": switch_entity},
            blocking=True,
        )
        await hass.async_block_till_done()
    assert kevin_stub._set_mode_calls[-1]["json"] == {"mode": "STAND_BY"}


async def test_api_401_relogin_once_then_auth_failure(
    hass: HomeAssistant, kevin_stub: KevinApiStub
) -> None:
    """One 401 triggers a single re-login; repeated 401 fails authentication."""
    kevin_stub.set_devices([DEVICE_ONE])
    session = async_get_clientsession(hass)
    client = KevinApiClient(session, TEST_BASE_URL, TEST_EMAIL, TEST_PASSWORD)

    with aioresponses() as mock:
        kevin_stub.apply(mock)
        kevin_stub.enable_single_devices_401_retry()
        await client.login()
        devices = await client.get_devices()
        assert len(devices) == 1
        assert kevin_stub.login_count == 2

    with aioresponses() as mock:

        def login_cb(url, **kwargs):
            kevin_stub.login_count += 1
            return CallbackResult(
                status=200,
                payload={
                    "accessToken": "access-token-2",
                    "idToken": "id-token-2",
                    "tokenType": "Bearer",
                    "expiresIn": 3600,
                },
            )

        def always_401(url, **kwargs):
            kevin_stub._record(url)
            return CallbackResult(status=401)

        mock.post(f"{TEST_BASE_URL}/v1/auth/login", callback=login_cb, repeat=True)
        mock.get(f"{TEST_BASE_URL}/v1/devices", callback=always_401, repeat=True)
        kevin_stub.login_count = 0
        await client.login()
        assert kevin_stub.login_count == 1
        with pytest.raises(KevinAuthError):
            await client.get_devices()
        assert kevin_stub.login_count == 2


async def test_dynamic_device_discovery_without_reload(
    hass: HomeAssistant, kevin_stub: KevinApiStub
) -> None:
    """A device appearing on a later poll adds entities without reload."""
    kevin_stub.set_devices([DEVICE_ONE])
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_EMAIL: TEST_EMAIL,
            CONF_PASSWORD: TEST_PASSWORD,
        },
    )
    entry.add_to_hass(hass)
    with aioresponses() as mock:
        kevin_stub.apply(mock)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    registry = er.async_get(hass)
    assert len(er.async_entries_for_config_entry(registry, entry.entry_id)) == 3

    kevin_stub.set_devices([DEVICE_ONE, DEVICE_TWO])
    coordinator = entry.runtime_data
    with aioresponses() as mock:
        kevin_stub.apply(mock)
        await coordinator.async_refresh()
        await hass.async_block_till_done()

    entities = er.async_entries_for_config_entry(registry, entry.entry_id)
    assert len(entities) == 6
    assert any(e.unique_id.startswith(f"{DEVICE_TWO['id']}_") for e in entities)


async def test_only_documented_kevin_endpoints_requested(
    hass: HomeAssistant, kevin_stub: KevinApiStub
) -> None:
    """Full setup and switch action must not call non-Kevin routes."""
    kevin_stub.set_devices([DEVICE_ONE])
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_EMAIL: TEST_EMAIL,
            CONF_PASSWORD: TEST_PASSWORD,
        },
    )
    entry.add_to_hass(hass)
    with aioresponses() as mock:
        kevin_stub.apply(mock)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    registry = er.async_get(hass)
    switch_entity = registry.async_get_entity_id(
        "switch", DOMAIN, f"{DEVICE_ONE['id']}_power"
    )
    with aioresponses() as mock:
        kevin_stub.apply(mock)
        await hass.services.async_call(
            switch.DOMAIN,
            "turn_on",
            {"entity_id": switch_entity},
            blocking=True,
        )
        await hass.async_block_till_done()

    assert_allowed_kevin_paths(kevin_stub.requested_paths)
    joined = " ".join(kevin_stub.requested_paths)
    assert "legacy" not in joined
    assert "auth0.com" not in joined
