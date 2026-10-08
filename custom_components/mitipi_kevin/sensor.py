"""Sensor platform for Mitipi Kevin."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import MitipiKevinConfigEntry
from .entity import MitipiKevinEntity, availability_from_snapshot, reported_mode
from .platform_helpers import async_setup_platform_entities


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MitipiKevinConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Kevin mode sensors."""

    def _factory(coordinator, device_id):
        return MitipiKevinModeSensor(coordinator, device_id)

    async_setup_platform_entities(entry, async_add_entities, _factory)


class MitipiKevinModeSensor(MitipiKevinEntity, SensorEntity):
    """Reported device mode."""

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
