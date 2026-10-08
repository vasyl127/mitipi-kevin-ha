"""The Mitipi Kevin integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from .const import PLATFORMS
from .coordinator import MitipiKevinCoordinator, build_client_from_entry

_LOGGER = logging.getLogger(__name__)

type MitipiKevinConfigEntry = ConfigEntry[MitipiKevinCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: MitipiKevinConfigEntry) -> bool:
    """Set up Mitipi Kevin from a config entry."""
    client = build_client_from_entry(hass, entry)
    coordinator = MitipiKevinCoordinator(hass, client, entry)
    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryAuthFailed:
        raise
    except Exception as err:
        raise ConfigEntryNotReady from err

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: MitipiKevinConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        entry.runtime_data = None
    return unload_ok
