"""Select platform for Mitipi Kevin scenes."""

from __future__ import annotations

import uuid
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import MitipiKevinConfigEntry
from .entity import MitipiKevinEntity, availability_from_snapshot
from .platform_helpers import async_setup_platform_entities


def _scene_option_label(scene: dict[str, Any], *, used_titles: set[str]) -> str:
    title = str(scene.get("title") or scene.get("id") or "Scene")
    if title not in used_titles:
        used_titles.add(title)
        return title
    environment = scene.get("environment")
    label = f"{title} ({environment})" if environment else f"{title} ({scene.get('id')})"
    used_titles.add(label)
    return label


def build_scene_option_map(scenes_payload: dict[str, Any] | None) -> dict[str, str]:
    """Map select option labels to scene ids."""
    if not scenes_payload:
        return {}
    scenes = scenes_payload.get("scenes")
    if not isinstance(scenes, list):
        return {}
    used: set[str] = set()
    mapping: dict[str, str] = {}
    for scene in scenes:
        if not isinstance(scene, dict) or not scene.get("id"):
            continue
        label = _scene_option_label(scene, used_titles=used)
        mapping[label] = str(scene["id"])
    return mapping


def active_scene_option(
    scenes_payload: dict[str, Any] | None,
    option_map: dict[str, str],
) -> str | None:
    """Return the select option for the first active scene id, if any."""
    if not scenes_payload or not option_map:
        return None
    active = scenes_payload.get("activeSceneIds")
    if not isinstance(active, list) or not active:
        return None
    active_id = str(active[0])
    for label, scene_id in option_map.items():
        if scene_id == active_id:
            return label
    return None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MitipiKevinConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Kevin scene selectors."""

    def _factory(coordinator, device_id):
        return MitipiKevinSceneSelect(coordinator, device_id)

    async_setup_platform_entities(entry, async_add_entities, _factory)


class MitipiKevinSceneSelect(MitipiKevinEntity, SelectEntity):
    """Apply a Kevin scene by title."""

    _attr_translation_key = "scene"

    def __init__(self, coordinator, device_id: str) -> None:
        super().__init__(
            coordinator,
            device_id,
            entity_key="scene",
            name_suffix="Scene",
        )

    @property
    def available(self) -> bool:
        availability = availability_from_snapshot(self.snapshot)
        return availability is not None and availability != "unknown"

    @property
    def option_map(self) -> dict[str, str]:
        snapshot = self.snapshot
        return build_scene_option_map(snapshot.scenes if snapshot else None)

    @property
    def options(self) -> list[str]:
        return list(self.option_map.keys())

    @property
    def current_option(self) -> str | None:
        snapshot = self.snapshot
        return active_scene_option(
            snapshot.scenes if snapshot else None,
            self.option_map,
        )

    async def async_select_option(self, option: str) -> None:
        scene_id = self.option_map.get(option)
        if not scene_id:
            return
        idempotency_key = uuid.uuid4().hex
        await self.coordinator.client.apply_scene(
            self._device_id,
            scene_id,
            idempotency_key,
        )
        await self.coordinator.async_request_refresh()
