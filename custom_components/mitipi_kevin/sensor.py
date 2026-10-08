"""Sensor platform for Mitipi Kevin."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import MitipiKevinConfigEntry
from .entity import (
    MitipiKevinEntity,
    availability_from_snapshot,
    firmware_version,
    reported_mode,
    subscription_from_snapshot,
)
from .platform_helpers import async_setup_platform_entities


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MitipiKevinConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Kevin sensors."""

    async_setup_platform_entities(
        entry, async_add_entities, lambda c, d: MitipiKevinModeSensor(c, d)
    )
    async_setup_platform_entities(
        entry, async_add_entities, lambda c, d: MitipiKevinFirmwareSensor(c, d)
    )
    async_setup_platform_entities(
        entry, async_add_entities, lambda c, d: MitipiKevinSubscriptionSensor(c, d)
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


class MitipiKevinSubscriptionSensor(MitipiKevinEntity, SensorEntity):
    """Subscription status from the Kevin API."""

    _attr_translation_key = "subscription"

    def __init__(self, coordinator, device_id: str) -> None:
        super().__init__(
            coordinator,
            device_id,
            entity_key="subscription",
            name_suffix="Subscription",
        )

    @property
    def available(self) -> bool:
        availability = availability_from_snapshot(self.snapshot)
        return availability is not None and availability != "unknown"

    @property
    def native_value(self) -> str | None:
        sub = subscription_from_snapshot(self.snapshot)
        if not sub:
            return None
        status = sub.get("status")
        return str(status) if status is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        sub = subscription_from_snapshot(self.snapshot)
        if not sub:
            return {}
        attrs: dict[str, Any] = {}
        for key, attr_key in (
            ("plan", "plan"),
            ("expiresAt", "expires_at"),
            ("remainingSeconds", "remaining_seconds"),
            ("source", "source"),
        ):
            if sub.get(key) is not None:
                attrs[attr_key] = sub[key]
        return attrs
