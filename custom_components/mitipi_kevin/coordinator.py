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
from .card_helpers import normalize_preferences
from .const import (
    CONF_EMAIL,
    CONF_PASSWORD,
    DOMAIN,
    MODE_CONFIRM_INTERVAL,
    MODE_CONFIRM_TIMEOUT,
    PARALLEL_UPDATES,
    PREFERENCES_POLL_EVERY,
    SCENES_POLL_EVERY,
    STALE_POLLS_ALLOWED,
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
    # Failed polls in a row for which this snapshot was carried over unchanged.
    stale_polls: int = 0


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
        # Account onboarding preferences; None until read. `preferences_state` is
        # "configured", "not_configured" or "unavailable" (route missing or failing).
        self.account_preferences: dict[str, Any] | None = None
        self.preferences_state = "unavailable"
        self._preferences_poll = 0
        self._summary_retry_after: dict[str, int] = {}
        self._summary_fallback_logged: set[str] = set()
        self._poll = 0
        self._failed_polls = 0
        self._confirm_tasks: dict[str, asyncio.Task] = {}

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

    async def _fetch_account_preferences(self) -> None:
        """Preferences poll is isolated: failures never affect device entities."""
        self._preferences_poll += 1
        known = self.preferences_state != "unavailable"
        if known and self._preferences_poll % PREFERENCES_POLL_EVERY:
            return
        try:
            status, data = await self.client.get_preferences_response()
        except KevinAuthError:
            raise
        except Exception:  # noqa: BLE001 - optional account data
            _LOGGER.debug("Account preferences temporarily unavailable", exc_info=True)
            return
        if status == 401:
            raise KevinAuthError
        if status != 200:
            if self.account_preferences is None:
                self.preferences_state = "unavailable"
            return
        self.apply_preferences_payload(data)

    def apply_preferences_payload(self, data: Any) -> None:
        """Store a GET/PATCH /v1/preferences body."""
        prefs = normalize_preferences(data)
        if prefs is not None:
            self.account_preferences = prefs
            self.preferences_state = "configured"
        elif isinstance(data, dict) and data.get("status") == "not_configured":
            self.account_preferences = None
            self.preferences_state = "not_configured"

    async def _fetch_device_scenes(self, device_id: str) -> dict[str, Any] | None:
        """Scene catalog for the select entity. Optional: only auth errors propagate."""
        path = f"/v1/devices/{device_id}/scenes"
        try:
            status, data = await self.client.get_json_response(path)
        except KevinAuthError:
            raise
        except Exception:  # noqa: BLE001 - scenes never decide device availability
            _LOGGER.debug("Device %s scenes fetch failed", device_id, exc_info=True)
            return None
        if status == 401:
            raise KevinAuthError
        if status == 200 and isinstance(data, dict):
            return data
        _LOGGER.debug("Device %s scenes unavailable (HTTP %s)", device_id, status)
        return None

    @property
    def failed_polls(self) -> int:
        """Polls in a row that failed as a whole (0 after a good poll)."""
        return self._failed_polls

    @property
    def summary_fallback_devices(self) -> frozenset[str]:
        """Devices currently read through /state and /capabilities instead of /summary."""
        return frozenset(self._summary_fallback_logged)

    def _previous(self, device_id: str) -> KevinDeviceSnapshot | None:
        return (self.data or {}).get(device_id)

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
        previous = self._previous(device_id)
        async with semaphore:
            # Scenes are read on the first poll and then every few polls; a failed read
            # keeps the previous catalog.
            scenes = previous.scenes if previous else None
            if scenes is None or self._poll % SCENES_POLL_EVERY == 0:
                scenes = await self._fetch_device_scenes(device_id) or scenes
            summary, needs_fallback = await self._fetch_summary_preferred(device_id)
            if summary is None and needs_fallback:
                summary = await self._build_summary_from_routes(device, device_id)
        return KevinDeviceSnapshot(device=device, summary=summary, scenes=scenes)

    def _carry_over(self, device_id: str) -> KevinDeviceSnapshot | None:
        """Previous snapshot for a Kevin whose poll failed, while it is still fresh enough."""
        previous = self._previous(device_id)
        if previous is None or previous.stale_polls >= STALE_POLLS_ALLOWED:
            return None
        return KevinDeviceSnapshot(
            device=previous.device,
            summary=previous.summary,
            scenes=previous.scenes,
            stale_polls=previous.stale_polls + 1,
        )

    async def _async_update_data(self) -> dict[str, KevinDeviceSnapshot]:
        self._tick_summary_backoff()
        self._poll += 1
        try:
            await self.client.ensure_authenticated()
            await self._fetch_account_subscription()
            await self._fetch_account_preferences()
            devices = await self.client.get_devices()
        except KevinAuthError as err:
            raise ConfigEntryAuthFailed from err
        except Exception as err:
            # A short API outage keeps the last known state instead of blanking every
            # entity; it surfaces once it lasts STALE_POLLS_ALLOWED polls.
            self._failed_polls += 1
            if self.data and self._failed_polls <= STALE_POLLS_ALLOWED:
                _LOGGER.debug(
                    "Kevin API poll failed (%s in a row); keeping last state", self._failed_polls
                )
                return {
                    device_id: snap
                    for device_id in self.data
                    if (snap := self._carry_over(device_id)) is not None
                }
            if isinstance(err, KevinConnectionError):
                raise UpdateFailed("Kevin API unavailable") from err
            raise UpdateFailed("Kevin API request failed") from err
        self._failed_polls = 0

        if not devices:
            return {}

        semaphore = asyncio.Semaphore(PARALLEL_UPDATES)
        snapshots = await asyncio.gather(
            *[self._fetch_device_details(device, semaphore) for device in devices],
            return_exceptions=True,
        )

        result: dict[str, KevinDeviceSnapshot] = {}
        for device, item in zip(devices, snapshots, strict=True):
            device_id = device_api_id(device)
            if isinstance(item, KevinAuthError):
                raise ConfigEntryAuthFailed from item
            if isinstance(item, BaseException):
                _LOGGER.debug("Device %s poll failed: %s", device_id, type(item).__name__)
                if (carried := self._carry_over(device_id)) is not None:
                    result[device_id] = carried
                continue
            result[device_id] = item
        return result

    async def _read_summary(self, device_id: str) -> dict[str, Any] | None:
        """One /summary read for a single Kevin; None on any non-auth failure."""
        try:
            status, data = await self.client.get_json_response(f"/v1/devices/{device_id}/summary")
        except KevinAuthError:
            raise
        except Exception:  # noqa: BLE001 - confirmation polling is best effort
            return None
        if status == 401:
            raise KevinAuthError
        return data if status == 200 and isinstance(data, dict) else None

    async def async_confirm_mode(self, device_id: str, mode: str) -> bool:
        """Poll one Kevin's summary until it reports `mode`, pushing every read to entities.

        The device usually confirms within a few seconds; the regular poll would only
        notice up to a minute later. Returns True once the mode is confirmed.
        """
        loop = asyncio.get_running_loop()
        deadline = loop.time() + MODE_CONFIRM_TIMEOUT
        while loop.time() < deadline:
            await asyncio.sleep(MODE_CONFIRM_INTERVAL)
            summary = await self._read_summary(device_id)
            previous = self._previous(device_id)
            if summary is None or previous is None:
                continue
            updated = dict(self.data or {})
            updated[device_id] = KevinDeviceSnapshot(
                device=previous.device, summary=summary, scenes=previous.scenes
            )
            self.async_set_updated_data(updated)
            if summary.get("mode") == mode:
                return True
        _LOGGER.debug("Device %s did not confirm mode %s in time", device_id, mode)
        return False

    def schedule_mode_confirmation(self, device_id: str, mode: str) -> None:
        """Start (or restart) confirmation polling for one Kevin in the background."""
        if (running := self._confirm_tasks.get(device_id)) and not running.done():
            running.cancel()
        task = self.config_entry.async_create_background_task(
            self.hass,
            self.async_confirm_mode(device_id, mode),
            f"{DOMAIN}_confirm_mode_{device_id}",
        )
        self._confirm_tasks[device_id] = task


def build_client_from_entry(hass: HomeAssistant, entry: ConfigEntry) -> KevinApiClient:
    """Create an API client from config entry data (password or Sign in with Mitipi)."""
    from homeassistant.helpers import config_entry_oauth2_flow

    from .api import create_client
    from .oauth import OAuthTokenProvider, async_register_implementation, is_oauth_entry

    if is_oauth_entry(entry):
        implementation = async_register_implementation(hass)
        session = config_entry_oauth2_flow.OAuth2Session(hass, entry, implementation)
        return create_client(hass, token_provider=OAuthTokenProvider(hass, entry, session))
    return create_client(
        hass,
        entry.data[CONF_EMAIL],
        entry.data[CONF_PASSWORD],
    )
