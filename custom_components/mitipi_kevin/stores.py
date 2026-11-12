"""Find the store that installed this integration: the Marketplace (HA 2026.11+) or HACS.

Home Assistant 2026.11 ships HACS as the built-in Marketplace integration and removes the HACS
custom integration on the first start. Both keep installed repositories in a manager with the
same shape (`repositories.get_by_full_name`, `data.async_write`, `coordinators`):

- the Marketplace manager is the `runtime_data` of the loaded `marketplace` config entry;
- HACS keeps its manager in `hass.data["hacs"]` (Home Assistant 2026.10 and older).

Neither is a public API, so callers treat every attribute access as optional.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntryState

from .environment import GITHUB_REPOSITORY

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

MARKETPLACE_DOMAIN = "marketplace"
HACS_DOMAIN = "hacs"


def get_marketplace(hass: HomeAssistant) -> Any | None:
    """The Marketplace manager when the Marketplace integration is loaded, else None."""
    for entry in hass.config_entries.async_entries(MARKETPLACE_DOMAIN):
        if entry.state is ConfigEntryState.LOADED:
            manager = getattr(entry, "runtime_data", None)
            if manager is not None:
                return manager
    return None


def marketplace_loaded(hass: HomeAssistant) -> bool:
    """True when the built-in Marketplace manages custom repositories (HA 2026.11+)."""
    return get_marketplace(hass) is not None


def get_hacs(hass: HomeAssistant) -> Any | None:
    """The HACS manager of Home Assistant 2026.10 and older, else None."""
    return hass.data.get(HACS_DOMAIN)


def installed_repository(store: Any) -> Any | None:
    """This integration's repository in a store, when the store installed it."""
    try:
        repository = store.repositories.get_by_full_name(GITHUB_REPOSITORY)
        if repository is None or not repository.data.installed:
            return None
    except Exception:  # noqa: BLE001 — store internals may change between versions
        _LOGGER.debug("Could not look up the repository in the store", exc_info=True)
        return None
    return repository


async def async_refresh_repository(store: Any) -> bool:
    """Ask a store to re-read this repository now, like its own "Update information" action.

    Returns False when the store does not track this repository or the call fails.
    """
    repository = installed_repository(store)
    if repository is None:
        return False
    try:
        await repository.update_repository(ignore_issues=True, force=True)
        await store.data.async_write()
        coordinator = getattr(store, "coordinators", {}).get(repository.data.category)
        if coordinator is not None:
            coordinator.async_update_listeners()
    except Exception:  # noqa: BLE001 — store internals may change between versions
        _LOGGER.debug("Could not refresh the repository in the store", exc_info=True)
        return False
    return True
