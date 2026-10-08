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
