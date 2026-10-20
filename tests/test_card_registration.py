"""Bundled Lovelace card registration and packaging checks."""

from __future__ import annotations

import subprocess
from pathlib import Path

from custom_components.mitipi_kevin.const import INTEGRATION_VERSION
from custom_components.mitipi_kevin.frontend import card_js_url

REPO_ROOT = Path(__file__).resolve().parents[1]
CARD_PATH = (
    REPO_ROOT / "custom_components" / "mitipi_kevin" / "www" / "kevin-presence-card.js"
)
SMOKE_SCRIPT = REPO_ROOT / "tests" / "js" / "card_registration_smoke.mjs"


def test_bundled_card_file_is_packaged() -> None:
    """The card script must ship inside the integration directory (not gitignored)."""
    assert CARD_PATH.is_file(), "kevin-presence-card.js must exist in www/"


def test_card_assets_are_packaged() -> None:
    """The window photo ships next to the card script; brand images ship with the integration."""
    www = CARD_PATH.parent
    assert (www / "kevin-photo-scene.webp").is_file()
    assert '"kevin-photo-scene.webp"' in CARD_PATH.read_text(encoding="utf-8")
    brand = REPO_ROOT / "custom_components" / "mitipi_kevin" / "brand"
    for name in ("icon.png", "icon@2x.png", "logo.png", "logo@2x.png"):
        assert (brand / name).is_file(), name


def test_card_js_url_matches_manifest_version() -> None:
    """Frontend module URL must track manifest version for cache busting."""
    assert card_js_url() == f"/mitipi_kevin/{INTEGRATION_VERSION}/kevin-presence-card.js"


def test_card_registration_node_smoke() -> None:
    """ES module load must register customCards and custom element tags."""
    result = subprocess.run(
        ["node", str(SMOKE_SCRIPT)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
