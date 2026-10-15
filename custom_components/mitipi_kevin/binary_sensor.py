"""Binary sensor platform for Mitipi Kevin."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import MitipiKevinConfigEntry
from .card_helpers import epoch_to_iso
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
        self._last_seen: float | None = None

    @property
    def available(self) -> bool:
        """Available whenever the Kevin is known, even if its connectivity is not.

        An unknown connectivity is reported as state `unknown` instead of making the
        entity unavailable, because Home Assistant drops all attributes of an
        unavailable entity and the card would lose the last seen time exactly when it
        needs it.
        """
        return super().available and self.snapshot is not None

    @property
    def is_on(self) -> bool | None:
        availability = availability_from_snapshot(self.snapshot)
        if availability is None or availability == "unknown":
            return None
        return availability == "online"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Last connectivity report, used by the card for "last seen".

        The newest known value is kept across polls that do not carry one (summary
        fallback, offline or unknown connectivity) and never moves backwards.
        """
        snapshot = self.snapshot
        raw = snapshot.summary.get("lastSeenAt") if snapshot and snapshot.summary else None
        if epoch_to_iso(raw) is not None:
            seconds = raw / 1000 if raw > 1e12 else float(raw)
            if self._last_seen is None or seconds > self._last_seen:
                self._last_seen = seconds
        last_seen = epoch_to_iso(self._last_seen)
        return {"last_seen": last_seen} if last_seen else {}
