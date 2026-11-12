"""Test helpers from whichever Home Assistant pytest plugin is installed.

Home Assistant 2026.11 and later: pytest-homeassistant (shipped with core).
Older releases: pytest-homeassistant-custom-component.
"""

try:
    from pytest_homeassistant.common import MockConfigEntry
except ImportError:  # Home Assistant before 2026.11
    from pytest_homeassistant_custom_component.common import MockConfigEntry

__all__ = ["MockConfigEntry"]
