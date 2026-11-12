"""Make new releases of this integration show up in Home Assistant without manual steps.

The Marketplace (Home Assistant 2026.11+) and HACS (2026.10 and older) re-read a repository
added from a link only every 48 hours, so a new release can stay invisible for days. This
module checks the latest GitHub release itself and, when it is newer than the installed
version, asks the store that installed the integration to refresh this repository, so its
update entity appears under Settings → Updates. The Marketplace is preferred: on 2026.11
HACS is removed. If neither store tracks the repository, a Repairs issue links to the
release instead.
"""

from __future__ import annotations

import logging
import re
from datetime import timedelta
from typing import Any

from aiohttp import ClientError, ClientTimeout
from homeassistant.const import EVENT_CORE_CONFIG_UPDATE
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_call_later, async_track_time_interval

from .const import DOMAIN, INTEGRATION_VERSION
from .environment import GITHUB_REPOSITORY
from .stores import async_refresh_repository, get_hacs, get_marketplace
from .update_icon import async_fix_hacs_update_icon

_LOGGER = logging.getLogger(__name__)

LATEST_RELEASE_URL = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/releases/latest"
RELEASES_URL = f"https://github.com/{GITHUB_REPOSITORY}/releases"
CHECK_INTERVAL = timedelta(hours=6)
FIRST_CHECK_DELAY = 120  # seconds; give the Marketplace or HACS time to finish starting
ISSUE_ID = "update_available"
_DATA_KEY = f"{DOMAIN}_update_check"

_VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


def parse_version(value: str | None) -> tuple[int, int, int] | None:
    """`v0.4.1` / `0.4.1` → (0, 4, 1); anything else (pre-releases, hashes) → None."""
    match = _VERSION_RE.match((value or "").strip())
    return tuple(int(part) for part in match.groups()) if match else None  # type: ignore[return-value]


def is_newer(latest: str | None, installed: str = INTEGRATION_VERSION) -> bool:
    """True only when both versions parse and `latest` is strictly higher."""
    a, b = parse_version(latest), parse_version(installed)
    return a is not None and b is not None and a > b


async def async_fetch_latest_tag(hass: HomeAssistant) -> str | None:
    """Tag of the latest published GitHub release, or None when GitHub is unreachable."""
    session = async_get_clientsession(hass)
    try:
        async with session.get(
            LATEST_RELEASE_URL,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": f"mitipi_kevin/{INTEGRATION_VERSION}",
            },
            timeout=ClientTimeout(total=20),
        ) as resp:
            if resp.status != 200:
                _LOGGER.debug("Latest release check returned HTTP %s", resp.status)
                return None
            data: dict[str, Any] = await resp.json()
    except (ClientError, TimeoutError, ValueError) as err:
        _LOGGER.debug("Latest release check failed: %s", err)
        return None
    if data.get("draft") or data.get("prerelease"):
        return None
    tag = data.get("tag_name")
    return tag if isinstance(tag, str) else None


async def async_refresh_store(hass: HomeAssistant) -> str | None:
    """Ask the store that installed this integration to re-read the repository now.

    Returns `marketplace` or `hacs` for the store that refreshed it, None when no store
    tracks this repository (manual install) or the refresh failed.
    """
    marketplace = get_marketplace(hass)
    if marketplace is not None and await async_refresh_repository(marketplace):
        return "marketplace"
    hacs = get_hacs(hass)
    if hacs is not None and await async_refresh_repository(hacs):
        await async_fix_hacs_update_icon(hass)
        return "hacs"
    return None


async def async_check_for_update(hass: HomeAssistant) -> str:
    """Run one check.

    Returns `current`, `marketplace`, `hacs`, `repair` or `unknown` (GitHub unreachable).
    """
    await async_fix_hacs_update_icon(hass)
    latest = await async_fetch_latest_tag(hass)
    if latest is None:
        return "unknown"
    if not is_newer(latest):
        ir.async_delete_issue(hass, DOMAIN, ISSUE_ID)
        return "current"
    if store := await async_refresh_store(hass):
        ir.async_delete_issue(hass, DOMAIN, ISSUE_ID)
        _LOGGER.info("Mitipi Kevin %s is available; %s refreshed", latest, store)
        return store
    ir.async_create_issue(
        hass,
        DOMAIN,
        ISSUE_ID,
        is_fixable=False,
        is_persistent=False,
        severity=ir.IssueSeverity.WARNING,
        learn_more_url=f"{RELEASES_URL}/tag/{latest}",
        translation_key=ISSUE_ID,
        translation_placeholders={"latest": latest, "installed": INTEGRATION_VERSION},
    )
    return "repair"


@callback
def async_setup_update_check(hass: HomeAssistant) -> CALLBACK_TYPE:
    """Start the periodic check once per Home Assistant, shared by all config entries.

    Returns a release callback; the timers stop when the last entry releases it.
    """
    state = hass.data.get(_DATA_KEY)
    if state is None:

        async def _run(_now: Any = None) -> None:
            await async_check_for_update(hass)

        @callback
        def _on_core_config(_event: Any) -> None:
            hass.async_create_task(async_fix_hacs_update_icon(hass))

        state = {
            "users": 0,
            "unsubs": [
                async_call_later(hass, FIRST_CHECK_DELAY, _run),
                async_track_time_interval(hass, _run, CHECK_INTERVAL),
                hass.bus.async_listen(EVENT_CORE_CONFIG_UPDATE, _on_core_config),
            ],
        }
        hass.data[_DATA_KEY] = state
    state["users"] += 1

    @callback
    def _release() -> None:
        current = hass.data.get(_DATA_KEY)
        if current is None:
            return
        current["users"] -= 1
        if current["users"] <= 0:
            for unsub in current["unsubs"]:
                unsub()
            hass.data.pop(_DATA_KEY, None)

    return _release
