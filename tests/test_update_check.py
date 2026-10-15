"""Release check that makes new versions reach Home Assistant's update list."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from aioresponses import aioresponses
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from custom_components.mitipi_kevin.const import DOMAIN, INTEGRATION_VERSION
from custom_components.mitipi_kevin.update_check import (
    ISSUE_ID,
    LATEST_RELEASE_URL,
    async_check_for_update,
    async_setup_update_check,
    is_newer,
    parse_version,
)


def test_version_parsing_and_comparison() -> None:
    assert parse_version("v0.4.2") == (0, 4, 2)
    assert parse_version("0.10.0") == (0, 10, 0)
    assert parse_version("ed25c83") is None
    assert parse_version("v1.0.0-beta.1") is None
    assert is_newer("v0.10.0", "0.9.9")
    assert not is_newer("v0.4.2", "0.4.2")
    assert not is_newer("v0.4.1", "0.4.2")
    assert not is_newer("garbage", "0.4.2")


def _bump(version: str) -> str:
    major, minor, patch = (int(p) for p in version.split("."))
    return f"v{major}.{minor}.{patch + 1}"


class _FakeRepository:
    def __init__(self, installed: bool = True) -> None:
        self.data = SimpleNamespace(installed=installed, category="integration")
        self.refreshed: list[dict] = []

    async def update_repository(self, **kwargs) -> None:
        self.refreshed.append(kwargs)


class _FakeHacs:
    def __init__(self, repository: _FakeRepository | None) -> None:
        self._repository = repository
        self.written = 0
        self.notified = 0
        hacs = self

        class _Coordinator:
            def async_update_listeners(self) -> None:
                hacs.notified += 1

        self.coordinators = {"integration": _Coordinator()}
        self.repositories = SimpleNamespace(get_by_full_name=lambda name: self._repository)
        self.data = SimpleNamespace(async_write=self._write)

    async def _write(self) -> None:
        self.written += 1


async def test_newer_release_refreshes_hacs(hass: HomeAssistant) -> None:
    repository = _FakeRepository()
    hacs = _FakeHacs(repository)
    hass.data["hacs"] = hacs
    with aioresponses() as mock:
        mock.get(LATEST_RELEASE_URL, payload={"tag_name": _bump(INTEGRATION_VERSION)})
        assert await async_check_for_update(hass) == "hacs"
    assert repository.refreshed == [{"ignore_issues": True, "force": True}]
    assert hacs.written == 1 and hacs.notified == 1
    assert ir.async_get(hass).async_get_issue(DOMAIN, ISSUE_ID) is None


async def test_newer_release_without_hacs_raises_repair(hass: HomeAssistant) -> None:
    latest = _bump(INTEGRATION_VERSION)
    with aioresponses() as mock:
        mock.get(LATEST_RELEASE_URL, payload={"tag_name": latest})
        assert await async_check_for_update(hass) == "repair"
    issue = ir.async_get(hass).async_get_issue(DOMAIN, ISSUE_ID)
    assert issue is not None
    assert issue.translation_placeholders == {"latest": latest, "installed": INTEGRATION_VERSION}
    assert issue.learn_more_url.endswith(f"/releases/tag/{latest}")

    # Once the installed version catches up, the repair goes away.
    with aioresponses() as mock:
        mock.get(LATEST_RELEASE_URL, payload={"tag_name": f"v{INTEGRATION_VERSION}"})
        assert await async_check_for_update(hass) == "current"
    assert ir.async_get(hass).async_get_issue(DOMAIN, ISSUE_ID) is None


async def test_repository_not_downloaded_through_hacs_raises_repair(hass: HomeAssistant) -> None:
    hass.data["hacs"] = _FakeHacs(_FakeRepository(installed=False))
    with aioresponses() as mock:
        mock.get(LATEST_RELEASE_URL, payload={"tag_name": _bump(INTEGRATION_VERSION)})
        assert await async_check_for_update(hass) == "repair"


@pytest.mark.parametrize(
    ("status", "payload"),
    [(403, {"message": "rate limited"}), (200, {"tag_name": "v9.9.9", "prerelease": True}), (200, {})],
)
async def test_unusable_github_answers_change_nothing(hass: HomeAssistant, status: int, payload: dict) -> None:
    repository = _FakeRepository()
    hass.data["hacs"] = _FakeHacs(repository)
    with aioresponses() as mock:
        mock.get(LATEST_RELEASE_URL, status=status, payload=payload)
        assert await async_check_for_update(hass) == "unknown"
    assert repository.refreshed == []
    assert ir.async_get(hass).async_get_issue(DOMAIN, ISSUE_ID) is None


async def test_scheduler_is_shared_and_released(hass: HomeAssistant) -> None:
    release_one = async_setup_update_check(hass)
    release_two = async_setup_update_check(hass)
    key = f"{DOMAIN}_update_check"
    assert hass.data[key]["users"] == 2
    release_one()
    assert hass.data[key]["users"] == 1
    release_two()
    assert key not in hass.data
