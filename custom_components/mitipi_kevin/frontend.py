"""Register the bundled Kevin Presence Lovelace card."""

from __future__ import annotations

from pathlib import Path

from homeassistant.components import frontend
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN, INTEGRATION_VERSION

_CARD_FILENAME = "kevin-presence-card.js"


@callback
def card_js_url() -> str:
    """Versioned URL for the bundled card script."""
    return f"/mitipi_kevin/{INTEGRATION_VERSION}/{_CARD_FILENAME}"


async def async_register_card(hass: HomeAssistant) -> None:
    """Serve the card script and register it with the frontend."""
    if hass.data.setdefault(DOMAIN, {}).get("card_registered"):
        return

    if hass.http is None:
        return

    www_dir = Path(__file__).parent / "www"
    card_path = www_dir / _CARD_FILENAME
    url_path = f"/mitipi_kevin/{INTEGRATION_VERSION}"

    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(
                url_path,
                str(www_dir),
                cache_headers=True,
            )
        ]
    )
    if not card_path.is_file():
        msg = "Bundled Kevin Presence card is missing"
        raise FileNotFoundError(msg)

    frontend.add_extra_js_url(hass, f"{url_path}/{_CARD_FILENAME}")
    hass.data[DOMAIN]["card_registered"] = True
