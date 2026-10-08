"""Button platform for Mitipi Kevin."""

from __future__ import annotations

import uuid

from homeassistant.components.button import ButtonEntity
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
    """Set up Kevin reboot button."""

    def _factory(coordinator, device_id):
        return MitipiKevinRebootButton(coordinator, device_id)

    async_setup_platform_entities(entry, async_add_entities, _factory)


class MitipiKevinRebootButton(MitipiKevinEntity, ButtonEntity):
    """Request a device reboot."""

    _attr_translation_key = "reboot"

    def __init__(self, coordinator, device_id: str) -> None:
        super().__init__(
            coordinator,
            device_id,
            entity_key="reboot",
            name_suffix="Reboot",
        )

    @property
    def available(self) -> bool:
        availability = availability_from_snapshot(self.snapshot)
        return availability is not None and availability != "unknown"

    async def async_press(self) -> None:
        idempotency_key = uuid.uuid4().hex
        await self.coordinator.client.reboot_device(self._device_id, idempotency_key)
        await self.coordinator.async_request_refresh()
