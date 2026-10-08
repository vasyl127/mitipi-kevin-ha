"""Sensor platform for Mitipi Kevin."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import MitipiKevinConfigEntry
from .coordinator import MitipiKevinCoordinator
from .entity import MitipiKevinEntity, availability_from_snapshot, firmware_version, reported_mode
from .platform_helpers import async_setup_platform_entities
from .subscription_helpers import subscription_state_attributes


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
    async_add_entities([MitipiKevinAccountSubscriptionSensor(coordinator, entry.entry_id)])


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
