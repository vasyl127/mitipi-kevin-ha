"""Device card entities and API actions."""

from __future__ import annotations

import re

from aioresponses import aioresponses
from homeassistant.components import button, select
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mitipi_kevin.const import CONF_EMAIL, CONF_PASSWORD, DOMAIN
from tests.conftest import (
    DEVICE_ONE,
    TEST_EMAIL,
    TEST_PASSWORD,
    KevinApiStub,
    scenes_payload,
    summary_payload,
)


async def _setup_one_device(hass: HomeAssistant, kevin_stub: KevinApiStub) -> MockConfigEntry:
    kevin_stub.set_devices([DEVICE_ONE])
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_EMAIL: TEST_EMAIL, CONF_PASSWORD: TEST_PASSWORD},
    )
    entry.add_to_hass(hass)
    with aioresponses() as mock:
        kevin_stub.apply(mock)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


async def test_firmware_sensor(hass: HomeAssistant, kevin_stub: KevinApiStub) -> None:
    """Firmware version is exposed from summary."""
    kevin_stub.summaries[DEVICE_ONE["id"]] = summary_payload(
        DEVICE_ONE, firmware_version="2.10"
    )
    await _setup_one_device(hass, kevin_stub)
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id("sensor", DOMAIN, f"{DEVICE_ONE['id']}_firmware")
    assert hass.states.get(entity_id).state == "2.10"


async def test_subscription_attributes_present_and_absent(
    hass: HomeAssistant, kevin_stub: KevinApiStub
) -> None:
    """Subscription sensor reflects status; optional fields become attributes only."""
    kevin_stub.summaries[DEVICE_ONE["id"]] = summary_payload(
        DEVICE_ONE,
        subscription={"status": "unknown", "source": "not_configured"},
    )
    entry = await _setup_one_device(hass, kevin_stub)
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        "sensor", DOMAIN, f"{DEVICE_ONE['id']}_subscription"
    )
    state = hass.states.get(entity_id)
    assert state.state == "unknown"
    assert state.attributes.get("source") == "not_configured"
    assert "plan" not in state.attributes
    assert "expires_at" not in state.attributes

    kevin_stub.summaries[DEVICE_ONE["id"]] = summary_payload(
        DEVICE_ONE,
        subscription={
            "status": "active",
            "plan": "premium",
            "expiresAt": "2030-01-01T00:00:00Z",
            "remainingSeconds": 3600,
            "source": "billing",
        },
    )
    coordinator = entry.runtime_data
    with aioresponses() as mock:
        kevin_stub.apply(mock)
        await coordinator.async_refresh()
        await hass.async_block_till_done()
    state = hass.states.get(entity_id)
    assert state.state == "active"
    assert state.attributes["plan"] == "premium"
    assert state.attributes["expires_at"] == "2030-01-01T00:00:00Z"
    assert state.attributes["remaining_seconds"] == 3600


async def test_scene_select_empty_active(hass: HomeAssistant, kevin_stub: KevinApiStub) -> None:
    """Scene select has no current option when activeSceneIds is empty."""
    kevin_stub.scenes[DEVICE_ONE["id"]] = scenes_payload(active_scene_ids=[])
    await _setup_one_device(hass, kevin_stub)
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id("select", DOMAIN, f"{DEVICE_ONE['id']}_scene")
    state = hass.states.get(entity_id)
    assert state.state in ("unknown", "unavailable", "")


async def test_scene_select_exposes_catalog_attributes(
    hass: HomeAssistant, kevin_stub: KevinApiStub
) -> None:
    """Scene select exposes catalog metadata for the Lovelace card."""
    kevin_stub.scenes[DEVICE_ONE["id"]] = scenes_payload()
    await _setup_one_device(hass, kevin_stub)
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id("select", DOMAIN, f"{DEVICE_ONE['id']}_scene")
    state = hass.states.get(entity_id)
    catalog = state.attributes.get("scene_catalog")
    assert isinstance(catalog, list)
    assert catalog[0]["title"] == "Cozy evening"
    assert catalog[0]["environment"] == "HOME"
    assert state.attributes.get("active_scene_ids") == []


async def test_scene_select_apply_scene(hass: HomeAssistant, kevin_stub: KevinApiStub) -> None:
    """Selecting a scene calls apply-scene with idempotency key."""
    kevin_stub.scenes[DEVICE_ONE["id"]] = scenes_payload()
    await _setup_one_device(hass, kevin_stub)
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id("select", DOMAIN, f"{DEVICE_ONE['id']}_scene")
    with aioresponses() as mock:
        kevin_stub.apply(mock)
        await hass.services.async_call(
            select.DOMAIN,
            "select_option",
            {"entity_id": entity_id, "option": "Cozy evening"},
            blocking=True,
        )
        await hass.async_block_till_done()
    assert len(kevin_stub._apply_scene_calls) == 1
    call = kevin_stub._apply_scene_calls[0]
    assert call["json"] == {"sceneId": "scene-home-1"}
    assert call["idempotency_key"]
    assert re.match(r"^[A-Za-z0-9._-]+$", call["idempotency_key"])


async def test_reboot_button_idempotency(hass: HomeAssistant, kevin_stub: KevinApiStub) -> None:
    """Reboot button sends reboot action with idempotency key."""
    await _setup_one_device(hass, kevin_stub)
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id("button", DOMAIN, f"{DEVICE_ONE['id']}_reboot")
    with aioresponses() as mock:
        kevin_stub.apply(mock)
        await hass.services.async_call(
            button.DOMAIN,
            "press",
            {"entity_id": entity_id},
            blocking=True,
        )
        await hass.async_block_till_done()
    assert len(kevin_stub._reboot_calls) == 1
    assert kevin_stub._reboot_calls[0]["idempotency_key"]
