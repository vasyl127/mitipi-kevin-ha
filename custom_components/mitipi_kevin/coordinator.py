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
    CONF_EMAIL,
    CONF_PASSWORD,
    DOMAIN,
    PARALLEL_UPDATES,
    SUMMARY_RETRY_INTERVAL_POLLS,
    UPDATE_INTERVAL,
)
from .device_snapshot_helpers import build_summary_from_device_routes
from .subscription_helpers import parse_account_subscription

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class KevinDeviceSnapshot:
    """Registry row plus summary and scene catalog."""

    device: dict[str, Any]
    summary: dict[str, Any] | None
    scenes: dict[str, Any] | None


def device_api_id(device: dict[str, Any]) -> str:
    """Stable API device identifier."""
    return str(device.get("id") or device.get("deviceId"))


class MitipiKevinCoordinator(DataUpdateCoordinator[dict[str, KevinDeviceSnapshot]]):
    """Poll account subscription, devices, summary, and scenes."""

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
        self.account_subscription: dict[str, Any] = {}
        self._summary_retry_after: dict[str, int] = {}
        self._summary_fallback_logged: set[str] = set()

    async def _fetch_account_subscription(self) -> None:
        """Subscription poll is isolated from device entity availability."""
        try:
            status, data = await self.client.get_json_response("/v1/subscription")
            self.account_subscription = parse_account_subscription(status, data)
        except KevinAuthError:
            raise
        except KevinConnectionError as err:
            _LOGGER.debug("Account subscription temporarily unavailable: %s", type(err).__name__)
            self.account_subscription = {"status": "unknown", "source": "read_error"}
        except Exception:
            _LOGGER.debug("Account subscription read failed", exc_info=True)
            self.account_subscription = {"status": "unknown", "source": "read_error"}

    async def _fetch_device_scenes(self, device_id: str) -> dict[str, Any] | None:
        path = f"/v1/devices/{device_id}/scenes"
        try:
            status, data = await self.client.get_json_response(path)
            if status == 401:
                raise KevinAuthError
            if status >= 500:
                raise KevinConnectionError
            if status == 200 and isinstance(data, dict):
                return data
        except KevinAuthError:
            raise
        except KevinConnectionError:
            raise
        except Exception:
            _LOGGER.debug("Device %s scenes fetch failed", device_id, exc_info=True)
        return None

    def _should_attempt_summary(self, device_id: str) -> bool:
        remaining = self._summary_retry_after.get(device_id, 0)
        return remaining <= 0

    def _defer_summary_retry(self, device_id: str) -> None:
        self._summary_retry_after[device_id] = SUMMARY_RETRY_INTERVAL_POLLS

    def _tick_summary_backoff(self) -> None:
        for device_id, remaining in list(self._summary_retry_after.items()):
            if remaining <= 1:
                self._summary_retry_after.pop(device_id, None)
            else:
                self._summary_retry_after[device_id] = remaining - 1

    async def _fetch_summary_preferred(
        self,
        device_id: str,
    ) -> tuple[dict[str, Any] | None, bool]:
        """Try /summary when not in backoff. Returns (summary, used_fallback)."""
        if not self._should_attempt_summary(device_id):
            return None, True

        path = f"/v1/devices/{device_id}/summary"
        status, data = await self.client.get_json_response(path)
        if status == 401:
            raise KevinAuthError
        if status >= 500:
            raise KevinConnectionError
        if status == 200 and isinstance(data, dict):
            self._summary_retry_after.pop(device_id, None)
            self._summary_fallback_logged.discard(device_id)
            return data, False

        if device_id not in self._summary_fallback_logged:
            _LOGGER.warning(
                "Device %s summary unavailable (HTTP %s); using /state and /capabilities",
                device_id,
                status,
            )
            self._summary_fallback_logged.add(device_id)
        self._defer_summary_retry(device_id)
        return None, True

    async def _build_summary_from_routes(
        self,
        device: dict[str, Any],
        device_id: str,
    ) -> dict[str, Any] | None:
        state: dict[str, Any] | None = None
        capabilities: dict[str, Any] | None = None

        state_path = f"/v1/devices/{device_id}/state"
        state_status, state_data = await self.client.get_json_response(state_path)
        if state_status == 401:
            raise KevinAuthError
        if state_status >= 500:
            raise KevinConnectionError
        if state_status == 200 and isinstance(state_data, dict):
            state = state_data

        caps_path = f"/v1/devices/{device_id}/capabilities"
        caps_status, caps_data = await self.client.get_json_response(caps_path)
        if caps_status == 401:
            raise KevinAuthError
        if caps_status >= 500:
            raise KevinConnectionError
        if caps_status == 200 and isinstance(caps_data, dict):
            capabilities = caps_data

        return build_summary_from_device_routes(device, state, capabilities)

    async def _fetch_device_details(
        self,
        device: dict[str, Any],
        semaphore: asyncio.Semaphore,
    ) -> KevinDeviceSnapshot:
        device_id = device_api_id(device)
        async with semaphore:
            scenes = await self._fetch_device_scenes(device_id)
            summary, needs_fallback = await self._fetch_summary_preferred(device_id)
            if summary is None and needs_fallback:
                summary = await self._build_summary_from_routes(device, device_id)
        return KevinDeviceSnapshot(device=device, summary=summary, scenes=scenes)

    async def _async_update_data(self) -> dict[str, KevinDeviceSnapshot]:
        self._tick_summary_backoff()
        try:
            await self.client.ensure_authenticated()
            await self._fetch_account_subscription()
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
        entry.data[CONF_EMAIL],
        entry.data[CONF_PASSWORD],
    )
