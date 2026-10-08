"""Switch platform for Mitipi Kevin."""

from __future__ import annotations

import uuid

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import MitipiKevinConfigEntry
from .const import MODE_ON, MODE_STAND_BY
from .entity import MitipiKevinEntity, availability_from_snapshot, reported_mode
from .platform_helpers import async_setup_platform_entities


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MitipiKevinConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Kevin power switches."""

    def _factory(coordinator, device_id):
        return MitipiKevinPowerSwitch(coordinator, device_id)

    async_setup_platform_entities(entry, async_add_entities, _factory)


class MitipiKevinPowerSwitch(MitipiKevinEntity, SwitchEntity):
    """Device power via set-mode ON / STAND_BY."""

    def __init__(self, coordinator, device_id: str) -> None:
        super().__init__(
            coordinator,
            device_id,
            entity_key="power",
            name_suffix="Power",
        )

    @property
    def available(self) -> bool:
        availability = availability_from_snapshot(self.snapshot)
        return availability is not None and availability != "unknown"

    @property
    def is_on(self) -> bool | None:
        mode = reported_mode(self.snapshot)
        if mode is None:
            return None
        return mode == MODE_ON

    async def _set_mode(self, mode: str) -> None:
        idempotency_key = uuid.uuid4().hex
        await self.coordinator.client.set_mode(self._device_id, mode, idempotency_key)
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self, **kwargs) -> None:
        await self._set_mode(MODE_ON)

    async def async_turn_off(self, **kwargs) -> None:
        await self._set_mode(MODE_STAND_BY)
