"""Shared entity helpers."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import KevinDeviceSnapshot, MitipiKevinCoordinator, device_api_id


def device_display_name(device: dict[str, Any]) -> str:
    """Prefer kevinDeviceId for entity/device naming."""
    kevin_id = device.get("kevinDeviceId")
    if kevin_id:
        return str(kevin_id)
    if name := device.get("name"):
        return str(name)
    return device_api_id(device)


def availability_from_snapshot(snapshot: KevinDeviceSnapshot | None) -> str | None:
    """Return API availability or None when state is missing."""
    if not snapshot or not snapshot.state:
        return None
    value = snapshot.state.get("availability")
    if value in ("online", "offline", "unknown"):
        return value
    return None


def reported_mode(snapshot: KevinDeviceSnapshot | None) -> str | None:
    """Return reported mode from state payload."""
    if not snapshot or not snapshot.state:
        return None
    reported = snapshot.state.get("reported") or snapshot.state.get("state", {}).get("reported")
    if isinstance(reported, dict) and reported.get("mode") is not None:
        return str(reported["mode"])
    return None


class MitipiKevinEntity(CoordinatorEntity[MitipiKevinCoordinator]):
    """Base entity for a Kevin device."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: MitipiKevinCoordinator,
        device_id: str,
        *,
        entity_key: str,
        name_suffix: str,
    ) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._entity_key = entity_key
        self._attr_unique_id = f"{device_id}_{entity_key}"
        self._attr_name = name_suffix

    @property
    def device_info(self) -> DeviceInfo:
        snapshot = self.coordinator.data.get(self._device_id)
        device = snapshot.device if snapshot else {"id": self._device_id}
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=device_display_name(device),
            manufacturer="Mitipi",
            model="Kevin",
        )

    @property
    def snapshot(self) -> KevinDeviceSnapshot | None:
        """Latest coordinator snapshot for this device."""
        return self.coordinator.data.get(self._device_id)
