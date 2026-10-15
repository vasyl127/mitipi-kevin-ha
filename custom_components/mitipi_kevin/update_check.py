"""Make new releases of this integration show up in Home Assistant without manual steps.

HACS re-reads custom (non-default) repositories only every 48 hours, counted from
Home Assistant's start, so frequent restarts mean it never notices a new release.
This module checks the latest GitHub release itself and, when it is newer than the
installed version, asks HACS to refresh this repository so its update entity appears
under Settings → Updates. If HACS cannot be reached, a Repairs issue links to the
release instead.
"""

from __future__ import annotations

import logging
import re
from datetime import timedelta
from typing import Any

from aiohttp import ClientError, ClientTimeout
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_call_later, async_track_time_interval

from .const import DOMAIN, INTEGRATION_VERSION

_LOGGER = logging.getLogger(__name__)

GITHUB_REPOSITORY = "vasyl127/mitipi-kevin-ha"
LATEST_RELEASE_URL = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/releases/latest"
RELEASES_URL = f"https://github.com/{GITHUB_REPOSITORY}/releases"
CHECK_INTERVAL = timedelta(hours=6)
FIRST_CHECK_DELAY = 120  # seconds; give HACS time to finish its own startup
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


async def async_refresh_hacs(hass: HomeAssistant) -> bool:
    """Ask HACS to re-read this repository now. False when HACS is absent or not tracking it.

    Uses the same calls as HACS's own "Update information" button. HACS has no public
    API for this, so every failure is caught and reported as False.
    """
    hacs = hass.data.get("hacs")
    if hacs is None:
        return False
    try:
        repository = hacs.repositories.get_by_full_name(GITHUB_REPOSITORY)
        if repository is None or not repository.data.installed:
            return False
        await repository.update_repository(ignore_issues=True, force=True)
        await hacs.data.async_write()
        coordinator = getattr(hacs, "coordinators", {}).get(repository.data.category)
        if coordinator is not None:
            coordinator.async_update_listeners()
    except Exception:  # noqa: BLE001 — HACS internals may change between versions
        _LOGGER.debug("Could not refresh the HACS repository", exc_info=True)
        return False
    return True


async def async_check_for_update(hass: HomeAssistant) -> str:
    """Run one check. Returns `current`, `hacs`, `repair` or `unknown` (GitHub unreachable)."""
    latest = await async_fetch_latest_tag(hass)
    if latest is None:
        return "unknown"
    if not is_newer(latest):
        ir.async_delete_issue(hass, DOMAIN, ISSUE_ID)
        return "current"
    if await async_refresh_hacs(hass):
        ir.async_delete_issue(hass, DOMAIN, ISSUE_ID)
        _LOGGER.info("Mitipi Kevin %s is available; HACS refreshed", latest)
        return "hacs"
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

        state = {
            "users": 0,
            "unsubs": [
                async_call_later(hass, FIRST_CHECK_DELAY, _run),
                async_track_time_interval(hass, _run, CHECK_INTERVAL),
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
