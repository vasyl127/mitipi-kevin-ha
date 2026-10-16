"""Point the HACS update entity at this integration's local brand icon on HA 2026.3+.

HACS still sets entity_picture to the legacy brands CDN, which has no entry for custom
integrations. homeassistant.customize is used instead so the Updates UI shows our shipped
icon without waiting for https://github.com/hacs/integration/issues/5171.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.const import MAJOR_VERSION, MINOR_VERSION
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_values import EntityValues

from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

_LOCAL_ENTITY_PICTURE = f"/api/brands/integration/{DOMAIN}/icon.png"

# `homeassistant.core_config.DATA_CUSTOMIZE` is a HassKey("hass_customize"); HassKey is a
# str, so the plain key works on every version. Importing core_config would break setup
# on Home Assistant releases older than that module (hacs.json allows 2024.4).
DATA_CUSTOMIZE = "hass_customize"


def local_brands_proxy_supported() -> bool:
    """True when Home Assistant serves integration brand icons via the local proxy."""
    return (MAJOR_VERSION, MINOR_VERSION) >= (2026, 3)


def _hacs_update_entity_id(hass: HomeAssistant) -> str | None:
    hacs = hass.data.get("hacs")
    if hacs is None:
        return None
    try:
        from .update_check import GITHUB_REPOSITORY

        repository = hacs.repositories.get_by_full_name(GITHUB_REPOSITORY)
    except Exception:  # noqa: BLE001 — HACS internals vary by version
        return None
    if repository is None:
        return None
    try:
        repo_id = str(repository.data.id)
    except Exception:  # noqa: BLE001
        return None
    return er.async_get(hass).async_get_entity_id("update", "hacs", repo_id)


def _apply_entity_picture_override(hass: HomeAssistant, entity_id: str) -> bool:
    """Merge entity_picture into the customize store unless the user set another URL."""
    customize = hass.data.get(DATA_CUSTOMIZE)
    if customize is None:
        customize = EntityValues()
        hass.data[DATA_CUSTOMIZE] = customize

    if customize._exact is None:
        customize._exact = {}

    exact = customize._exact
    current = exact.get(entity_id, {}).get("entity_picture")
    if current is not None and current != _LOCAL_ENTITY_PICTURE:
        return False

    if current == _LOCAL_ENTITY_PICTURE:
        return True

    entry = dict(exact.get(entity_id, {}))
    entry["entity_picture"] = _LOCAL_ENTITY_PICTURE
    exact[entity_id] = entry
    EntityValues.get.cache_clear()
    return True


def _trigger_state_write(hass: HomeAssistant, entity_id: str) -> None:
    try:
        from homeassistant.helpers.entity_component import DATA_INSTANCES

        entity_comp = hass.data.get(DATA_INSTANCES, {}).get("update")
        if entity_comp is None:
            return
        entity_obj = entity_comp.get_entity(entity_id)
        if entity_obj is None:
            return
        entity_obj.async_write_ha_state()
    except Exception:  # noqa: BLE001
        _LOGGER.debug("Could not refresh HACS update entity state", exc_info=True)


async def async_fix_hacs_update_icon(hass: HomeAssistant) -> bool:
    """Apply the local brand icon override on the HACS update entity, when possible."""
    try:
        if not local_brands_proxy_supported():
            return False
        entity_id = _hacs_update_entity_id(hass)
        if entity_id is None:
            return False
        if not _apply_entity_picture_override(hass, entity_id):
            return False
        _trigger_state_write(hass, entity_id)
        return True
    except Exception:  # noqa: BLE001
        _LOGGER.debug("Could not fix HACS update icon", exc_info=True)
        return False
