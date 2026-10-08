"""Shared platform setup helpers."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.helpers.entity import Entity

    from . import MitipiKevinConfigEntry
    from .coordinator import MitipiKevinCoordinator


def async_setup_platform_entities(
    entry: MitipiKevinConfigEntry,
    async_add_entities: Callable[[list[Entity]], None],
    entity_factory: Callable[[MitipiKevinCoordinator, str], Entity],
) -> None:
    """Register entities for all devices and add new ones on coordinator updates."""
    coordinator = entry.runtime_data
    known_devices: set[str] = set()

    def _add_entities() -> None:
        new_entities: list[Entity] = []
        for device_id in coordinator.data:
            if device_id in known_devices:
                continue
            known_devices.add(device_id)
            new_entities.append(entity_factory(coordinator, device_id))
        if new_entities:
            async_add_entities(new_entities)

    _add_entities()
    entry.async_on_unload(coordinator.async_add_listener(_add_entities))
