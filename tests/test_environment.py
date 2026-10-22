"""The stage and production repositories differ only in their deployment target.

These checks keep every place that names the target in agreement, so a merge between the
two repositories cannot ship a build that talks to one API but updates from the other.
"""

import json
import re
from pathlib import Path

from custom_components.mitipi_kevin import const, environment, update_check

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "custom_components" / "mitipi_kevin"

TARGETS = {
    "stage": {
        "api": "https://stage-mitipi-api.teamvoy.com/api",
        "repository": "vasyl127/mitipi-kevin-ha",
        "name": "Mitipi Kevin (Stage)",
    },
    "production": {
        "api": "https://mitipi-api.teamvoy.com/api",
        "repository": "teamvoydev/mitipi-kevin",
        "name": "Mitipi Kevin",
    },
}


def _target():
    assert environment.ENVIRONMENT in TARGETS, environment.ENVIRONMENT
    return TARGETS[environment.ENVIRONMENT]


def test_api_and_repository_match_the_environment():
    target = _target()
    # conftest points const.KEVIN_API_BASE_URL at a test server, so check the source.
    assert target["api"] == environment.KEVIN_API_BASE_URL
    assert "KEVIN_API_BASE_URL = ENVIRONMENT_API_BASE_URL" in (PKG / "const.py").read_text()
    assert target["repository"] == environment.GITHUB_REPOSITORY
    assert target["repository"] == update_check.GITHUB_REPOSITORY
    latest = f"https://api.github.com/repos/{target['repository']}/releases/latest"
    assert latest == update_check.LATEST_RELEASE_URL


def test_manifest_and_hacs_metadata_match_the_environment():
    target = _target()
    url = f"https://github.com/{target['repository']}"
    manifest = json.loads((PKG / "manifest.json").read_text())
    assert manifest["name"] == target["name"]
    assert manifest["documentation"] == url
    assert manifest["issue_tracker"] == f"{url}/issues"
    assert manifest["version"] == const.INTEGRATION_VERSION
    hacs = json.loads((ROOT / "hacs.json").read_text())
    assert hacs["name"] == target["name"]


def test_readme_and_card_point_at_this_repository():
    target = _target()
    url = f"https://github.com/{target['repository']}"
    readme = (ROOT / "README.md").read_text()
    assert f"add `{url}` as category **Integration**" in readme
    assert f"(`{target['api']}`" in readme
    card = (PKG / "www" / "kevin-presence-card.js").read_text()
    assert re.search(r'documentationURL: "([^"]+)"', card).group(1) == url


def test_no_leftover_hosts_from_the_other_environment():
    _target()
    others = [t for name, t in TARGETS.items() if name != environment.ENVIRONMENT]
    # environment.py is left out: its docstring names both repositories on purpose.
    files = [PKG / "manifest.json", ROOT / "hacs.json", PKG / "www" / "kevin-presence-card.js"]
    for other in others:
        for path in files:
            text = path.read_text()
            assert other["repository"] not in text, (path, other["repository"])
            assert f'"{other["api"]}"' not in text, (path, other["api"])
    assert "marmash" not in (PKG / "environment.py").read_text() + (PKG / "const.py").read_text()
