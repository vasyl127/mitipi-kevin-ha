"""Diagnostics for Mitipi Kevin (Settings -> Devices & services -> Download diagnostics).

The download is meant to be attached to a support ticket, so it carries what helps
to explain a problem (versions, API target, poll health, per-device state) and
nothing that identifies or authenticates the user: credentials, tokens, e-mail
addresses and device names are never included.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_EMAIL, CONF_PASSWORD, INTEGRATION_VERSION
from .coordinator import KevinDeviceSnapshot, MitipiKevinCoordinator
from .environment import ENVIRONMENT, KEVIN_API_BASE_URL

TO_REDACT = {CONF_EMAIL, CONF_PASSWORD, "title", "unique_id"}

# Subscription fields that describe the plan, not the person or the payment.
_SUBSCRIPTION_FIELDS = (
    "status",
    "source",
    "plan_code",
    "tier",
    "interval",
    "is_trial",
    "cancel_at_period_end",
)


def _device_diagnostics(snapshot: KevinDeviceSnapshot) -> dict[str, Any]:
    summary = snapshot.summary or {}
    scenes = snapshot.scenes or {}
    return {
        # API ids identify the hardware for support, not the user; names may.
        "api_device_id": snapshot.device.get("id") or snapshot.device.get("deviceId"),
        "availability": summary.get("availability"),
        "mode": summary.get("mode"),
        "firmware_version": summary.get("firmwareVersion"),
        "summary_available": snapshot.summary is not None,
        "scene_count": len(scenes.get("scenes") or []),
        "active_scene_count": len(scenes.get("activeSceneIds") or []),
        "stale_polls": snapshot.stale_polls,
    }


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return redacted diagnostics for one Kevin account."""
    coordinator: MitipiKevinCoordinator | None = entry.runtime_data
    payload: dict[str, Any] = {
        "integration": {
            "version": INTEGRATION_VERSION,
            "environment": ENVIRONMENT,
            "api_base_url": KEVIN_API_BASE_URL,
        },
        "entry": async_redact_data(
            {
                "title": entry.title,
                "version": entry.version,
                "unique_id": entry.unique_id,
                "data": dict(entry.data),
                "options": dict(entry.options),
            },
            TO_REDACT,
        ),
    }
    if coordinator is None:
        payload["coordinator"] = None
        return payload

    subscription = coordinator.account_subscription or {}
    payload["coordinator"] = {
        "last_update_success": coordinator.last_update_success,
        "update_interval_seconds": (
            coordinator.update_interval.total_seconds() if coordinator.update_interval else None
        ),
        "failed_polls_in_a_row": coordinator.failed_polls,
        "devices_on_summary_fallback": len(coordinator.summary_fallback_devices),
        "preferences_state": coordinator.preferences_state,
        "account_subscription": {
            key: subscription.get(key) for key in _SUBSCRIPTION_FIELDS if key in subscription
        },
    }
    payload["devices"] = [
        _device_diagnostics(snapshot) for snapshot in (coordinator.data or {}).values()
    ]
    return payload
