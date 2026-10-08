"""The Mitipi Kevin integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from .const import CONF_EMAIL, CONF_PASSWORD, PLATFORMS
from .coordinator import MitipiKevinCoordinator, build_client_from_entry
from .frontend import async_register_card

_LOGGER = logging.getLogger(__name__)

type MitipiKevinConfigEntry = ConfigEntry[MitipiKevinCoordinator]


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Drop legacy per-entry API URL overrides; credentials stay on the approved host."""
    if entry.version == 1:
        data = {
            CONF_EMAIL: entry.data[CONF_EMAIL],
            CONF_PASSWORD: entry.data[CONF_PASSWORD],
        }
        hass.config_entries.async_update_entry(entry, data=data, version=2)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: MitipiKevinConfigEntry) -> bool:
    """Set up Mitipi Kevin from a config entry."""
    await async_register_card(hass)
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
