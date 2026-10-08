"""Binary sensor platform for Mitipi Kevin."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import MitipiKevinConfigEntry
from .entity import MitipiKevinEntity, availability_from_snapshot
from .platform_helpers import async_setup_platform_entities


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MitipiKevinConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Kevin connectivity binary sensors."""

    def _factory(coordinator, device_id):
        return MitipiKevinConnectivitySensor(coordinator, device_id)

    async_setup_platform_entities(entry, async_add_entities, _factory)


class MitipiKevinConnectivitySensor(MitipiKevinEntity, BinarySensorEntity):
    """Device connectivity from API availability."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator, device_id: str) -> None:
        super().__init__(
            coordinator,
            device_id,
            entity_key="connectivity",
            name_suffix="Connectivity",
        )

    @property
    def available(self) -> bool:
        availability = availability_from_snapshot(self.snapshot)
        return availability is not None and availability != "unknown"

    @property
    def is_on(self) -> bool | None:
        availability = availability_from_snapshot(self.snapshot)
        if availability is None or availability == "unknown":
            return None
        return availability == "online"
