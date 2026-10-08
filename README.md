# Mitipi Kevin for Home Assistant (HACS)

Production-oriented custom integration that connects Home Assistant to **Mitipi Kevin** through the Kevin HTTP API only. Home Assistant never talks to Auth0, Cognito, AWS Lambda, MQTT, or legacy AWS routes directly—credentials are exchanged once with `POST /v1/auth/login`, and all device traffic uses Bearer + `x-auth0-id-token` headers on Kevin API paths.

## HACS installation

1. In HACS → **Custom repositories**, add `https://github.com/vasyl127/mitipi-kevin-ha` as category **Integration**.
2. Install **Mitipi Kevin** and restart Home Assistant.
3. Go to **Settings → Devices & services → Add integration** and search for **Mitipi Kevin**.

Alternatively, copy `custom_components/mitipi_kevin` into your Home Assistant `config/custom_components/` directory and restart.

## Configuration flow

The config flow collects **email** and **password** only. All traffic uses the fixed Kevin API base URL (`https://mitipi.marmash.dev/api`); the host is not user-configurable.

On submit, the integration validates credentials by logging in and calling `GET /v1/devices`. Access and ID tokens are kept **in memory only** and are not written to the config entry or logs.

If the API returns `401` during normal operation, Home Assistant starts a **re-authentication** flow that asks only for email and password.

## Entity model

Each Kevin device exposes entities with stable `unique_id` = `{apiDeviceId}_{role}`:

| Platform | Role | Behavior |
| -------- | ---- | -------- |
| `sensor` | `mode` | Reported mode (`ON` / `STAND_BY`); unavailable when offline/unknown |
| `sensor` | `firmware` | Firmware version string from `/summary` |
| `sensor` | `subscription` | Status string; `plan`, `expires_at`, `remaining_seconds`, `source` as attributes when present |
| `binary_sensor` | `connectivity` | `online` → on, `offline` → off, `unknown` → unavailable |
| `switch` | `power` | `turn_on` / `turn_off` → `set-mode` with idempotency key; refresh after `202`, no optimistic state |
| `select` | `scene` | Scene titles as options; empty `activeSceneIds` → no selection; `select_option` → `apply-scene` only |
| `button` | `reboot` | `press` → reboot action with idempotency key |

The coordinator polls `GET /v1/devices/{id}/summary` and `GET /v1/devices/{id}/scenes` per device (bounded concurrency). Dynamic discovery adds entities when new devices appear.

### Subscription data

The API may return `{ "status": "unknown", "source": "not_configured" }` when upstream billing is not wired. That is a normal steady state—the integration does not invent plans or trial periods.

## Kevin Presence Lovelace card (bundled)

Version **0.2.0** ships `kevin-presence-card.js`. After the integration loads, Home Assistant registers the script automatically—**no manual Lovelace resource entry** is required.

Add a card in the UI or YAML (use your power switch entity id):

```yaml
type: custom:kevin-presence-card
entity: switch.kevin_z40189_power
theme: ambient
size: standard
```

### Card configuration

| Key | Required | Values | Default |
| --- | -------- | ------ | ------- |
| `entity` | yes | Kevin **power** switch `entity_id` | — |
| `theme` | no | `ambient`, `minimal`, `contrast` | `ambient` |
| `size` | no | `compact`, `standard`, `expanded` | `standard` |

Sibling entities (mode, connectivity, firmware, subscription, scene, reboot) are resolved via the device and entity registries on the same Kevin device—not by renaming patterns.

### Sizes

- **compact** (~112px, card size 2): name, confirmed power, connectivity text, primary command.
- **standard** (~256px, card size 5): adds beacon, full-width power command, scene entry.
- **expanded** (~440px, card size 8): adds firmware, serial, subscription block, low-emphasis reboot.

### Themes

All themes use Home Assistant CSS variables (`--card-background-color`, `--primary-text-color`, `--secondary-text-color`, `--divider-color`, `--primary-color`, `--ha-card-border-radius`):

- **ambient** — soft radial accent halo, accent-tinted primary button.
- **minimal** — neutral ring and small accent marker, no extra decoration.
- **contrast** — outlined controls using primary text color for borders.

Power control is a **command button** (not an optimistic toggle): the card waits for the switch entity to report the target state after `switch.turn_on` / `switch.turn_off`. Scene apply uses `select.select_option` only; reboot uses `button.press` after confirmation.

## Development

Requires Python 3.12+.

```bash
pip install "homeassistant==2024.12.5" pytest pytest-asyncio pytest-homeassistant-custom-component ruff aioresponses
ruff check .
pytest
node --check custom_components/mitipi_kevin/www/kevin-presence-card.js
```

**Home Assistant compatibility:** developed and tested against Home Assistant **2024.12.5** (minimum declared in `hacs.json`: **2024.4.0**).

## License

MIT — see [LICENSE](LICENSE).
