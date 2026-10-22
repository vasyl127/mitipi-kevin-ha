"""HACS update entity icon override for Home Assistant 2026.3+ local brands."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from homeassistant.core_config import DATA_CUSTOMIZE as HA_DATA_CUSTOMIZE
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_component import DATA_INSTANCES
from homeassistant.helpers.entity_values import EntityValues
from homeassistant.setup import async_setup_component

from custom_components.mitipi_kevin.const import DOMAIN
from custom_components.mitipi_kevin.update_check import GITHUB_REPOSITORY
from custom_components.mitipi_kevin.update_icon import (
    DATA_CUSTOMIZE,
    async_fix_hacs_update_icon,
    local_brands_proxy_supported,
)

LOCAL_ENTITY_PICTURE = f"/api/brands/integration/{DOMAIN}/icon.png"
REPO_ID = 987654321


class _FakeRepository:
    def __init__(self, *, installed: bool = True, repo_id: int = REPO_ID) -> None:
        self.data = SimpleNamespace(installed=installed, category="integration", id=repo_id)


class _FakeHacs:
    def __init__(self, repository: _FakeRepository | None) -> None:
        self.repositories = SimpleNamespace(
            get_by_full_name=lambda _name: repository,
        )


class _CdnUpdateEntity(Entity):
    """Mimics HACS entity_picture pointing at the legacy CDN."""

    _attr_should_poll = False

    @property
    def entity_picture(self) -> str:
        return f"https://brands.home-assistant.io/_/{DOMAIN}/icon.png"


@pytest.fixture
def enable_local_brands(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "custom_components.mitipi_kevin.update_icon.local_brands_proxy_supported",
        lambda: True,
    )


def _register_hacs_update_entity(hass, repo_id: int = REPO_ID) -> str:
    registry = er.async_get(hass)
    entry = registry.async_get_or_create(
        "update",
        "hacs",
        suggested_object_id="mitipi_kevin",
        unique_id=str(repo_id),
    )
    return entry.entity_id


def test_customize_key_matches_home_assistant() -> None:
    """The plain key must stay equal to HA's HassKey, or the override is silently ignored."""
    assert DATA_CUSTOMIZE == HA_DATA_CUSTOMIZE


async def test_no_op_when_local_brands_unsupported(hass) -> None:
    assert local_brands_proxy_supported() is False
    hass.data["hacs"] = _FakeHacs(_FakeRepository())
    _register_hacs_update_entity(hass)
    assert await async_fix_hacs_update_icon(hass) is False


async def test_no_op_without_hacs(hass, enable_local_brands) -> None:
    assert await async_fix_hacs_update_icon(hass) is False


async def test_no_op_without_repository(hass, enable_local_brands) -> None:
    hass.data["hacs"] = _FakeHacs(None)
    assert await async_fix_hacs_update_icon(hass) is False


async def test_no_op_without_entity_registry_entry(hass, enable_local_brands) -> None:
    hass.data["hacs"] = _FakeHacs(_FakeRepository())
    assert await async_fix_hacs_update_icon(hass) is False


async def test_creates_customize_store_when_missing(hass, enable_local_brands) -> None:
    hass.data.pop(DATA_CUSTOMIZE, None)
    hass.data["hacs"] = _FakeHacs(_FakeRepository())
    entity_id = _register_hacs_update_entity(hass)
    assert await async_fix_hacs_update_icon(hass) is True
    customize = hass.data[DATA_CUSTOMIZE]
    assert customize.get(entity_id)["entity_picture"] == LOCAL_ENTITY_PICTURE


async def test_user_entity_picture_is_preserved(hass, enable_local_brands) -> None:
    hass.data["hacs"] = _FakeHacs(_FakeRepository())
    entity_id = _register_hacs_update_entity(hass)
    user_url = "https://example.com/my-icon.png"
    hass.data[DATA_CUSTOMIZE] = EntityValues(exact={entity_id: {"entity_picture": user_url}})
    EntityValues.get.cache_clear()
    assert await async_fix_hacs_update_icon(hass) is False
    assert hass.data[DATA_CUSTOMIZE].get(entity_id)["entity_picture"] == user_url


async def test_broken_hacs_internals_return_false(hass, enable_local_brands) -> None:
    class _BrokenHacs:
        repositories = SimpleNamespace(
            get_by_full_name=lambda _name: (_ for _ in ()).throw(RuntimeError("broken")),
        )

    hass.data["hacs"] = _BrokenHacs()
    _register_hacs_update_entity(hass)
    assert await async_fix_hacs_update_icon(hass) is False


async def test_state_attribute_shows_local_url_after_write(hass, enable_local_brands) -> None:
    hass.data["hacs"] = _FakeHacs(_FakeRepository())
    entity_id = _register_hacs_update_entity(hass)
    await async_setup_component(hass, "update", {})
    stub = _CdnUpdateEntity()
    stub.entity_id = entity_id
    stub.hass = hass
    hass.data[DATA_INSTANCES]["update"]._entities[entity_id] = stub

    assert await async_fix_hacs_update_icon(hass) is True
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.attributes.get("entity_picture") == LOCAL_ENTITY_PICTURE


async def test_uses_repository_id_as_hacs_unique_id(hass, enable_local_brands) -> None:
    """HACS 2.0.5 sets _attr_unique_id = str(repository.data.id)."""
    repo_id = 42424242
    hass.data["hacs"] = _FakeHacs(_FakeRepository(repo_id=repo_id))
    entity_id = _register_hacs_update_entity(hass, repo_id=repo_id)
    assert await async_fix_hacs_update_icon(hass) is True
    assert hass.data[DATA_CUSTOMIZE].get(entity_id)["entity_picture"] == LOCAL_ENTITY_PICTURE
    assert GITHUB_REPOSITORY.count("/") == 1
