"""Entities and service behind the KEVIN® card v6: now playing, schedule, preferences."""

from __future__ import annotations

from datetime import date

import pytest
from aioresponses import aioresponses
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mitipi_kevin.card_helpers import (
    activity_from_state,
    format_activity_id,
    normalize_preferences,
    schedule_windows,
    weekly_hours,
)
from custom_components.mitipi_kevin.const import CONF_EMAIL, CONF_PASSWORD, DOMAIN
from tests.conftest import (
    DEVICE_ONE,
    TEST_EMAIL,
    TEST_PASSWORD,
    KevinApiStub,
    assert_allowed_kevin_paths,
    summary_payload,
)

SCHEDULES = [
    {
        "pattern": {"startTime": "18:00:00", "endTime": "23:00:00", "dates": ["Mon", "Tue"]},
        "enabled": True,
    },
    {
        "pattern": {"startTime": "09:00:00", "endTime": "12:00:00", "dates": ["Sat"]},
        "enabled": False,
    },
    {
        "pattern": {"startTime": "22:00:00", "endTime": "02:00:00", "dates": ["Fri"]},
        "enabled": True,
    },
    {
        "pattern": {"startTime": "17:30:00", "endTime": "24:00:00", "dates": ["Sun"]},
        "enabled": True,
    },
]


def test_schedule_windows_recurring_disabled_and_overnight() -> None:
    windows = schedule_windows(SCHEDULES, today=date(2026, 10, 14))
    assert windows[0] == [[18.0, 23.0]]
    assert windows[1] == [[18.0, 23.0]]
    assert windows[4] == [[22.0, 24.0]]
    assert windows[5] == [[0.0, 2.0]]
    assert windows[6] == [[17.5, 24.0]]
    assert weekly_hours(windows) == 20.5


def test_schedule_windows_one_off_dates_only_count_this_week() -> None:
    one_off = [
        {
            "pattern": {
                "startTime": "10:00:00",
                "endTime": "11:00:00",
                "dates": ["2026-10-15", "2026-10-30"],
            }
        },
    ]
    windows = schedule_windows(one_off, today=date(2026, 10, 14))
    assert windows[3] == [[10.0, 11.0]]
    assert sum(len(day) for day in windows) == 1


def test_schedule_windows_rejects_garbage() -> None:
    assert schedule_windows("nope") == [[] for _ in range(7)]
    bad = [{"pattern": {"startTime": "25:00", "endTime": "x", "dates": ["Mon"]}}, 3, None]
    assert schedule_windows(bad) == [[] for _ in range(7)]


def test_activity_helpers() -> None:
    assert format_activity_id("onb-cozy_time") == "Cozy Time"
    state = {
        "reported": {"activity": {"current": {"id": "onb-kitchen-mode"}}},
        "activitySince": 1791882000,
    }
    activity = activity_from_state(state)
    assert activity is not None
    assert activity["title"] == "Kitchen Mode"
    assert activity["since"].startswith("2026-10-")
    assert activity_from_state({"reported": {}}) is None


def test_normalize_preferences_allow_list() -> None:
    prefs = normalize_preferences(
        {
            "status": "configured",
            "preferences": {
                "environment": "BUSINESS",
                "characteristics": {"petsAllowed": True, "kids": True, "userId": True},
                "occupancyLevel": 12,
                "energyLevel": 3,
                "selectionId": "nope",
            },
        }
    )
    assert prefs == {
        "environment": "BUSINESS",
        "characteristics": {
            "customersPresent": False,
            "callsAndMeetings": False,
            "deliveryAndLogistics": False,
            "petsAllowed": True,
        },
        "occupancy_level": 10.0,
        "energy_level": 3.0,
    }
    assert normalize_preferences({"status": "not_configured"}) is None


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


def _entity(hass: HomeAssistant, domain: str, unique_id: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(domain, DOMAIN, unique_id)
    assert entity_id, unique_id
    return entity_id


async def test_now_playing_schedule_and_last_seen_from_summary(
    hass: HomeAssistant, kevin_stub: KevinApiStub
) -> None:
    summary = summary_payload(DEVICE_ONE)
    summary["activity"] = {
        "id": "onb-cozy-time",
        "title": "Cozy Time",
        "group": "Evening at home",
        "since": 1791882000,
    }
    summary["schedules"] = SCHEDULES
    summary["lastSeenAt"] = 1791882862
    kevin_stub.summaries[DEVICE_ONE["id"]] = summary
    await _setup(hass, kevin_stub)

    activity = hass.states.get(_entity(hass, "sensor", f"{DEVICE_ONE['id']}_activity"))
    assert activity.state == "Cozy Time"
    assert activity.attributes["group"] == "Evening at home"
    assert activity.attributes["activity_id"] == "onb-cozy-time"
    assert activity.attributes["since"].startswith("2026-10-")

    schedule = hass.states.get(_entity(hass, "sensor", f"{DEVICE_ONE['id']}_schedule"))
    assert float(schedule.state) == 20.5
    assert schedule.attributes["windows"][0] == [[18.0, 23.0]]

    conn = hass.states.get(_entity(hass, "binary_sensor", f"{DEVICE_ONE['id']}_connectivity"))
    assert conn.attributes["last_seen"].startswith("2026-10-")
    assert_allowed_kevin_paths(kevin_stub.requested_paths)


async def test_old_api_without_card_fields_degrades(
    hass: HomeAssistant, kevin_stub: KevinApiStub
) -> None:
    """A deployed API without the new fields keeps every device entity working."""
    kevin_stub.preferences_status = 404
    await _setup(hass, kevin_stub)
    activity = hass.states.get(_entity(hass, "sensor", f"{DEVICE_ONE['id']}_activity"))
    assert activity.state == "unknown"
    schedule = hass.states.get(_entity(hass, "sensor", f"{DEVICE_ONE['id']}_schedule"))
    assert schedule.state == "unavailable"
    prefs = hass.states.get(_entity(hass, "sensor", _pref_uid(hass)))
    assert prefs.state == "unavailable"
    power = hass.states.get(_entity(hass, "switch", f"{DEVICE_ONE['id']}_power"))
    assert power.state == "on"


def _pref_uid(hass: HomeAssistant) -> str:
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    return f"{entry.entry_id}_preferences"


async def test_activity_falls_back_to_state_route(
    hass: HomeAssistant, kevin_stub: KevinApiStub
) -> None:
    kevin_stub.default_summary_status = 403
    kevin_stub.set_devices([DEVICE_ONE])
    kevin_stub.device_states[DEVICE_ONE["id"]] = {
        "availability": "online",
        "reported": {
            "mode": "ON",
            "activity": {"current": {"id": "onb-cooking-mode"}},
            "schedules": SCHEDULES[:1],
        },
        "activitySince": 1791882000,
        "reportedMetadata": {"connected": {"timestamp": 1791882862}},
    }
    await _setup(hass, kevin_stub)
    activity = hass.states.get(_entity(hass, "sensor", f"{DEVICE_ONE['id']}_activity"))
    assert activity.state == "Cooking Mode"
    schedule = hass.states.get(_entity(hass, "sensor", f"{DEVICE_ONE['id']}_schedule"))
    assert float(schedule.state) == 10.0
    conn = hass.states.get(_entity(hass, "binary_sensor", f"{DEVICE_ONE['id']}_connectivity"))
    assert "last_seen" in conn.attributes


async def test_preferences_sensor_and_service(
    hass: HomeAssistant, kevin_stub: KevinApiStub
) -> None:
    await _setup(hass, kevin_stub)
    entity_id = _entity(hass, "sensor", _pref_uid(hass))
    state = hass.states.get(entity_id)
    assert state.state == "HOME"
    assert state.attributes["characteristics"] == {
        "kids": True,
        "teens": False,
        "dogs": True,
        "cats": False,
    }
    assert state.attributes["occupancy_level"] == 5.1

    with aioresponses() as mock:
        kevin_stub.apply(mock)
        await hass.services.async_call(
            DOMAIN,
            "set_preferences",
            {
                "entity_id": entity_id,
                "characteristics": {"cats": True},
                "energy_level": 7,
            },
            blocking=True,
        )
    assert kevin_stub.preferences_patch_calls == [
        {"characteristics": {"cats": True}, "energyLevel": 7.0}
    ]
    state = hass.states.get(entity_id)
    assert state.attributes["characteristics"]["cats"] is True
    assert state.attributes["energy_level"] == 7.0
    assert_allowed_kevin_paths(kevin_stub.requested_paths)


async def test_set_preferences_rejects_foreign_toggle_and_api_errors(
    hass: HomeAssistant, kevin_stub: KevinApiStub
) -> None:
    await _setup(hass, kevin_stub)
    entity_id = _entity(hass, "sensor", _pref_uid(hass))
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            DOMAIN,
            "set_preferences",
            {"entity_id": entity_id, "characteristics": {"forkliftTraffic": True}},
            blocking=True,
        )
    assert kevin_stub.preferences_patch_calls == []

    kevin_stub.preferences_patch_status = 502
    with aioresponses() as mock, pytest.raises(HomeAssistantError):
        kevin_stub.apply(mock)
        await hass.services.async_call(
            DOMAIN, "set_preferences", {"entity_id": entity_id, "energy_level": 2}, blocking=True
        )
    assert hass.states.get(entity_id).attributes["energy_level"] == 4.9


async def test_device_named_after_account_device_name(
    hass: HomeAssistant, kevin_stub: KevinApiStub
) -> None:
    await _setup(hass, kevin_stub)
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, DEVICE_ONE["id"])})
    assert device.name == "Living room"
    assert device.serial_number == "K-DEVICEONE"
