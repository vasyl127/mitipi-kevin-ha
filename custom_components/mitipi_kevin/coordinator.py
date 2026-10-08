"""Data update coordinator for Mitipi Kevin devices."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import KevinApiClient, KevinAuthError, KevinConnectionError
from .const import (
    CONF_BASE_URL,
    CONF_EMAIL,
    CONF_PASSWORD,
    DOMAIN,
    PARALLEL_UPDATES,
    UPDATE_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class KevinDeviceSnapshot:
    """Registry row plus live state and capabilities."""

    device: dict[str, Any]
    state: dict[str, Any] | None
    capabilities: dict[str, Any] | None


def device_api_id(device: dict[str, Any]) -> str:
    """Stable API device identifier."""
    return str(device.get("id") or device.get("deviceId"))


class MitipiKevinCoordinator(DataUpdateCoordinator[dict[str, KevinDeviceSnapshot]]):
    """Poll devices, state, and capabilities."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        client: KevinApiClient,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.client = client
        self.config_entry = entry

    async def _fetch_device_details(
        self,
        device: dict[str, Any],
        semaphore: asyncio.Semaphore,
    ) -> KevinDeviceSnapshot:
        device_id = device_api_id(device)
        async with semaphore:
            state: dict[str, Any] | None = None
            capabilities: dict[str, Any] | None = None
            try:
                state, capabilities = await asyncio.gather(
                    self.client.get_device_state(device_id),
                    self.client.get_device_capabilities(device_id),
                )
            except KevinAuthError:
                raise
            except KevinConnectionError as err:
                _LOGGER.debug("Device %s detail fetch failed: %s", device_id, type(err).__name__)
            except Exception:
                _LOGGER.debug("Device %s detail fetch failed", device_id, exc_info=True)
        return KevinDeviceSnapshot(device=device, state=state, capabilities=capabilities)

    async def _async_update_data(self) -> dict[str, KevinDeviceSnapshot]:
        try:
            await self.client.ensure_authenticated()
            devices = await self.client.get_devices()
        except KevinAuthError as err:
            raise ConfigEntryAuthFailed from err
        except KevinConnectionError as err:
            raise UpdateFailed("Kevin API unavailable") from err
        except Exception as err:
            raise UpdateFailed("Kevin API request failed") from err

        if not devices:
            return {}

        semaphore = asyncio.Semaphore(PARALLEL_UPDATES)
        snapshots = await asyncio.gather(
            *[self._fetch_device_details(device, semaphore) for device in devices],
            return_exceptions=True,
        )

        result: dict[str, KevinDeviceSnapshot] = {}
        for item in snapshots:
            if isinstance(item, KevinAuthError):
                raise ConfigEntryAuthFailed from item
            if isinstance(item, BaseException):
                continue
            device_id = device_api_id(item.device)
            result[device_id] = item
        return result


def build_client_from_entry(hass: HomeAssistant, entry: ConfigEntry) -> KevinApiClient:
    """Create an API client from config entry data."""
    from .api import create_client

    return create_client(
        hass,
        entry.data[CONF_BASE_URL],
        entry.data[CONF_EMAIL],
        entry.data[CONF_PASSWORD],
    )
