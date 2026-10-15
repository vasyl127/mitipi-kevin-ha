"""Card state stays readable through slow mode changes and flaky polls (MA-977, MA-980)."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from aioresponses import aioresponses
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mitipi_kevin.const import (
    CONF_EMAIL,
    CONF_PASSWORD,
    DOMAIN,
    STALE_POLLS_ALLOWED,
)
from custom_components.mitipi_kevin.device_snapshot_helpers import last_seen_from_metadata
from tests.conftest import DEVICE_ONE, TEST_EMAIL, TEST_PASSWORD, KevinApiStub, summary_payload

LAST_SEEN = 1792000000  # epoch seconds (October 2026)


def _summary(**kwargs: Any) -> dict[str, Any]:
    last_seen = kwargs.pop("last_seen", None)
    payload = summary_payload(DEVICE_ONE, **kwargs)
    if last_seen is not None:
        payload["lastSeenAt"] = last_seen
    return payload


async def _setup(hass: HomeAssistant, stub: KevinApiStub) -> MockConfigEntry:
    stub.set_devices([DEVICE_ONE])
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_EMAIL: TEST_EMAIL, CONF_PASSWORD: TEST_PASSWORD}
    )
    entry.add_to_hass(hass)
    with aioresponses() as mock:
        stub.apply(mock)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


def _entity(hass: HomeAssistant, domain: str, key: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(domain, DOMAIN, f"{DEVICE_ONE['id']}_{key}")
    assert entity_id
    return entity_id


async def _refresh(hass: HomeAssistant, stub: KevinApiStub, entry: MockConfigEntry) -> None:
    with aioresponses() as mock:
        stub.apply(mock)
        await entry.runtime_data.async_refresh()
        await hass.async_block_till_done()


async def test_failed_summary_keeps_last_state_for_a_few_polls(
    hass: HomeAssistant, kevin_stub: KevinApiStub
) -> None:
    """One 5xx on /summary must not blank the card; a lasting outage still surfaces."""
    kevin_stub.summaries[DEVICE_ONE["id"]] = _summary(mode="ON", last_seen=LAST_SEEN)
    entry = await _setup(hass, kevin_stub)
    power = _entity(hass, "switch", "power")
    conn = _entity(hass, "binary_sensor", "connectivity")
    assert hass.states.get(power).state == "on"

    kevin_stub.default_summary_status = 502
    for _ in range(STALE_POLLS_ALLOWED):
        await _refresh(hass, kevin_stub, entry)
        assert hass.states.get(power).state == "on"
        assert hass.states.get(conn).state == "on"
        assert hass.states.get(conn).attributes["last_seen"].startswith("2026-")

    await _refresh(hass, kevin_stub, entry)
    assert hass.states.get(power).state == "unavailable"

    kevin_stub.default_summary_status = 200
    await _refresh(hass, kevin_stub, entry)
    assert hass.states.get(power).state == "on"


async def test_api_outage_keeps_last_state(hass: HomeAssistant, kevin_stub: KevinApiStub) -> None:
    """A failing device list is tolerated for STALE_POLLS_ALLOWED polls."""
    entry = await _setup(hass, kevin_stub)
    power = _entity(hass, "switch", "power")
    kevin_stub.devices_status = 503
    await _refresh(hass, kevin_stub, entry)
    assert entry.runtime_data.last_update_success
    assert hass.states.get(power).state == "on"
    for _ in range(STALE_POLLS_ALLOWED):
        await _refresh(hass, kevin_stub, entry)
    assert hass.states.get(power).state == "unavailable"


async def test_scenes_failure_never_affects_the_device(
    hass: HomeAssistant, kevin_stub: KevinApiStub
) -> None:
    """/scenes is optional: its failure keeps power and connectivity, and the old catalog."""
    entry = await _setup(hass, kevin_stub)
    power = _entity(hass, "switch", "power")
    scene = _entity(hass, "select", "scene")
    options = hass.states.get(scene).attributes["options"]
    kevin_stub.scenes_status = 502
    entry.runtime_data._poll = 4  # next poll reads scenes again
    await _refresh(hass, kevin_stub, entry)
    assert hass.states.get(power).state == "on"
    assert hass.states.get(scene).attributes["options"] == options


async def test_scenes_are_not_read_on_every_poll(
    hass: HomeAssistant, kevin_stub: KevinApiStub
) -> None:
    entry = await _setup(hass, kevin_stub)
    kevin_stub.requested_paths.clear()
    await _refresh(hass, kevin_stub, entry)
    assert not any(p.endswith("/scenes") for p in kevin_stub.requested_paths)
    assert any(p.endswith("/summary") for p in kevin_stub.requested_paths)


async def test_last_seen_survives_unknown_connectivity(
    hass: HomeAssistant, kevin_stub: KevinApiStub
) -> None:
    """MA-977: the card keeps "last seen" when the device turns unknown/offline."""
    kevin_stub.summaries[DEVICE_ONE["id"]] = _summary(availability="online", last_seen=LAST_SEEN)
    entry = await _setup(hass, kevin_stub)
    conn = _entity(hass, "binary_sensor", "connectivity")
    first = hass.states.get(conn).attributes["last_seen"]

    kevin_stub.summaries[DEVICE_ONE["id"]] = _summary(availability="unknown")
    await _refresh(hass, kevin_stub, entry)
    state = hass.states.get(conn)
    assert state.state == "unknown"
    assert state.attributes["last_seen"] == first

    kevin_stub.summaries[DEVICE_ONE["id"]] = _summary(
        availability="offline", last_seen=LAST_SEEN - 600
    )
    await _refresh(hass, kevin_stub, entry)
    state = hass.states.get(conn)
    assert state.state == "off"
    assert state.attributes["last_seen"] == first  # never moves backwards


async def test_mode_change_is_confirmed_quickly(
    hass: HomeAssistant, kevin_stub: KevinApiStub
) -> None:
    """After set-mode the integration reads only the summary until the new mode shows up."""
    kevin_stub.summaries[DEVICE_ONE["id"]] = _summary(mode="STAND_BY")
    entry = await _setup(hass, kevin_stub)
    power = _entity(hass, "switch", "power")
    assert hass.states.get(power).state == "off"
    coordinator = entry.runtime_data
    reads = {"n": 0}

    async def fake_summary(device_id: str):
        reads["n"] += 1
        return _summary(mode="ON" if reads["n"] >= 2 else "STAND_BY")

    with (
        patch("custom_components.mitipi_kevin.coordinator.MODE_CONFIRM_INTERVAL", 0),
        patch.object(coordinator, "_read_summary", side_effect=fake_summary),
    ):
        assert await coordinator.async_confirm_mode(DEVICE_ONE["id"], "ON")
        await hass.async_block_till_done()
    assert reads["n"] == 2
    assert hass.states.get(power).state == "on"


async def test_mode_confirmation_gives_up(hass: HomeAssistant, kevin_stub: KevinApiStub) -> None:
    kevin_stub.summaries[DEVICE_ONE["id"]] = _summary(mode="STAND_BY")
    entry = await _setup(hass, kevin_stub)
    coordinator = entry.runtime_data

    async def never(device_id: str):
        return None

    with (
        patch("custom_components.mitipi_kevin.coordinator.MODE_CONFIRM_INTERVAL", 0.01),
        patch("custom_components.mitipi_kevin.coordinator.MODE_CONFIRM_TIMEOUT", 0.05),
        patch.object(coordinator, "_read_summary", side_effect=never),
    ):
        assert not await coordinator.async_confirm_mode(DEVICE_ONE["id"], "ON")


def test_last_seen_from_metadata() -> None:
    assert last_seen_from_metadata({"connected": {"timestamp": 5}, "mode": {"timestamp": 9}}) == 5
    assert last_seen_from_metadata({"mode": {"timestamp": 9}, "fw": {"timestamp": 7}}) == 9
    assert last_seen_from_metadata({"mode": {}}) is None
    assert last_seen_from_metadata(None) is None
