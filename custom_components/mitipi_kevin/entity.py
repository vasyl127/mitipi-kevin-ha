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
    """Return API availability or None when summary is missing."""
    if not snapshot or not snapshot.summary:
        return None
    value = snapshot.summary.get("availability")
    if value in ("online", "offline", "unknown"):
        return value
    return None


def reported_mode(snapshot: KevinDeviceSnapshot | None) -> str | None:
    """Return reported mode from summary payload."""
    if not snapshot or not snapshot.summary:
        return None
    mode = snapshot.summary.get("mode")
    if mode is not None:
        return str(mode)
    return None


def firmware_version(snapshot: KevinDeviceSnapshot | None) -> str | None:
    """Return firmware version string from summary."""
    if not snapshot or not snapshot.summary:
        return None
    fw = snapshot.summary.get("firmwareVersion")
    return str(fw) if fw is not None else None


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
        summary_device = (
            snapshot.summary.get("device")
            if snapshot and snapshot.summary and isinstance(snapshot.summary.get("device"), dict)
            else None
        )
        if summary_device:
            device = {**device, **summary_device}
        serial = device.get("kevinDeviceId")
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=device_display_name(device),
            manufacturer="Mitipi",
            model="Kevin",
            serial_number=str(serial) if serial else None,
        )

    @property
    def snapshot(self) -> KevinDeviceSnapshot | None:
        """Latest coordinator snapshot for this device."""
        return self.coordinator.data.get(self._device_id)
