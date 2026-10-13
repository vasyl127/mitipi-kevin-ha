"""Sensor platform for Mitipi Kevin."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_platform
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import MitipiKevinConfigEntry
from .api import KevinApiError, KevinAuthError, KevinConnectionError
from .card_helpers import (
    CHARACTERISTICS_BY_ENVIRONMENT,
    ENVIRONMENTS,
    LEVEL_MAX,
    LEVEL_MIN,
    activity_from_summary,
    schedule_windows,
    weekly_hours,
)
from .const import SERVICE_SET_PREFERENCES
from .coordinator import MitipiKevinCoordinator
from .entity import MitipiKevinEntity, availability_from_snapshot, firmware_version, reported_mode
from .platform_helpers import async_setup_platform_entities
from .subscription_helpers import subscription_state_attributes

_LEVEL = vol.All(vol.Coerce(float), vol.Range(min=LEVEL_MIN, max=LEVEL_MAX))
SET_PREFERENCES_SCHEMA = {
    vol.Optional("environment"): vol.In(ENVIRONMENTS),
    vol.Optional("characteristics"): vol.Schema({cv.string: cv.boolean}),
    vol.Optional("occupancy_level"): _LEVEL,
    vol.Optional("energy_level"): _LEVEL,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MitipiKevinConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Kevin sensors."""
    coordinator = entry.runtime_data

    async_setup_platform_entities(
        entry, async_add_entities, lambda c, d: MitipiKevinModeSensor(c, d)
    )
    async_setup_platform_entities(
        entry, async_add_entities, lambda c, d: MitipiKevinFirmwareSensor(c, d)
    )
    async_setup_platform_entities(
        entry, async_add_entities, lambda c, d: MitipiKevinActivitySensor(c, d)
    )
    async_setup_platform_entities(
        entry, async_add_entities, lambda c, d: MitipiKevinScheduleSensor(c, d)
    )
    async_add_entities(
        [
            MitipiKevinAccountSubscriptionSensor(coordinator, entry.entry_id),
            MitipiKevinPreferencesSensor(coordinator, entry.entry_id),
        ]
    )

    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        SERVICE_SET_PREFERENCES,
        SET_PREFERENCES_SCHEMA,
        "async_set_preferences",
    )


class MitipiKevinModeSensor(MitipiKevinEntity, SensorEntity):
    """Reported device mode."""

    _attr_translation_key = "mode"

    def __init__(self, coordinator, device_id: str) -> None:
        super().__init__(
            coordinator,
            device_id,
            entity_key="mode",
            name_suffix="Mode",
        )

    @property
    def available(self) -> bool:
        availability = availability_from_snapshot(self.snapshot)
        return availability is not None and availability not in ("unknown", "offline")

    @property
    def native_value(self) -> str | None:
        return reported_mode(self.snapshot)


class MitipiKevinFirmwareSensor(MitipiKevinEntity, SensorEntity):
    """Device firmware version."""

    _attr_translation_key = "firmware"

    def __init__(self, coordinator, device_id: str) -> None:
        super().__init__(
            coordinator,
            device_id,
            entity_key="firmware",
            name_suffix="Firmware",
        )

    @property
    def available(self) -> bool:
        availability = availability_from_snapshot(self.snapshot)
        return availability is not None and availability != "unknown"

    @property
    def native_value(self) -> str | None:
        return firmware_version(self.snapshot)


class MitipiKevinActivitySensor(MitipiKevinEntity, SensorEntity):
    """What KEVIN is playing now (reported, read-only)."""

    _attr_translation_key = "activity"
    _attr_icon = "mdi:waveform"

    def __init__(self, coordinator, device_id: str) -> None:
        super().__init__(
            coordinator,
            device_id,
            entity_key="activity",
            name_suffix="Now playing",
        )

    @property
    def available(self) -> bool:
        availability = availability_from_snapshot(self.snapshot)
        return availability is not None and availability != "unknown"

    @property
    def _activity(self) -> dict[str, Any] | None:
        snapshot = self.snapshot
        return activity_from_summary(snapshot.summary if snapshot else None)

    @property
    def native_value(self) -> str | None:
        activity = self._activity
        return activity["title"] if activity else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        activity = self._activity
        if not activity:
            return {}
        return {
            attr: activity[key]
            for key, attr in (("id", "activity_id"), ("group", "group"), ("since", "since"))
            if key in activity
        }


class MitipiKevinScheduleSensor(MitipiKevinEntity, SensorEntity):
    """Weekly Presence schedule: state is scheduled hours per week."""

    _attr_translation_key = "schedule"
    _attr_icon = "mdi:calendar-clock"
    _attr_native_unit_of_measurement = UnitOfTime.HOURS
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, device_id: str) -> None:
        super().__init__(
            coordinator,
            device_id,
            entity_key="schedule",
            name_suffix="Schedule",
        )

    def _raw_schedules(self) -> list[Any] | None:
        snapshot = self.snapshot
        raw = snapshot.summary.get("schedules") if snapshot and snapshot.summary else None
        return raw if isinstance(raw, list) else None

    @property
    def available(self) -> bool:
        return self._raw_schedules() is not None

    @property
    def native_value(self) -> float | None:
        raw = self._raw_schedules()
        return weekly_hours(schedule_windows(raw)) if raw is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        raw = self._raw_schedules()
        if raw is None:
            return {}
        return {"windows": schedule_windows(raw)}


class MitipiKevinAccountSubscriptionSensor(CoordinatorEntity[MitipiKevinCoordinator], SensorEntity):
    """Account-level Kevin subscription (one per config entry)."""

    _attr_has_entity_name = True
    _attr_translation_key = "account_subscription"
    _attr_name = "Subscription"

    def __init__(self, coordinator: MitipiKevinCoordinator, entry_id: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry_id}_account_subscription"
        self._attr_device_info = None

    @property
    def available(self) -> bool:
        return bool(self.coordinator.account_subscription)

    @property
    def native_value(self) -> str | None:
        sub = self.coordinator.account_subscription
        status = sub.get("status")
        return str(status) if status is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return subscription_state_attributes(self.coordinator.account_subscription)


class MitipiKevinPreferencesSensor(CoordinatorEntity[MitipiKevinCoordinator], SensorEntity):
    """Account onboarding preferences: state is the environment."""

    _attr_has_entity_name = True
    _attr_translation_key = "preferences"
    _attr_name = "Preferences"
    _attr_icon = "mdi:home-heart"

    def __init__(self, coordinator: MitipiKevinCoordinator, entry_id: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry_id}_preferences"
        self._attr_device_info = None

    @property
    def available(self) -> bool:
        return self.coordinator.preferences_state != "unavailable"

    @property
    def native_value(self) -> str | None:
        prefs = self.coordinator.account_preferences
        if prefs:
            return prefs["environment"]
        return "not_configured" if self.coordinator.preferences_state == "not_configured" else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        prefs = self.coordinator.account_preferences
        if not prefs:
            return {}
        return {key: value for key, value in prefs.items() if key != "environment"}

    async def async_set_preferences(self, **kwargs: Any) -> None:
        """Change environment, lifestyle toggles or levels (mirrors the Mitipi app)."""
        body: dict[str, Any] = {}
        environment = kwargs.get("environment")
        if environment is not None:
            body["environment"] = environment
        current = self.coordinator.account_preferences or {}
        target_env = environment or current.get("environment")
        characteristics = kwargs.get("characteristics")
        if characteristics is not None:
            allowed = CHARACTERISTICS_BY_ENVIRONMENT.get(str(target_env), ())
            unknown = sorted(set(characteristics) - set(allowed))
            if unknown:
                msg = f"Unknown lifestyle toggles for {target_env}: {', '.join(unknown)}"
                raise HomeAssistantError(msg)
            body["characteristics"] = {key: bool(value) for key, value in characteristics.items()}
        if (occupancy := kwargs.get("occupancy_level")) is not None:
            body["occupancyLevel"] = occupancy
        if (energy := kwargs.get("energy_level")) is not None:
            body["energyLevel"] = energy
        if not body:
            raise HomeAssistantError("Nothing to change")
        try:
            data = await self.coordinator.client.patch_preferences(body)
        except KevinAuthError as err:
            self.coordinator.config_entry.async_start_reauth(self.hass)
            raise HomeAssistantError("Kevin account needs to sign in again") from err
        except KevinConnectionError as err:
            raise HomeAssistantError("Kevin API unavailable") from err
        except KevinApiError as err:
            raise HomeAssistantError(str(err) or "Preferences update rejected") from err
        self.coordinator.apply_preferences_payload(data)
        self.coordinator.async_update_listeners()
