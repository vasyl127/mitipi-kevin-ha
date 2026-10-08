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
| `sensor` | `account_subscription` | **One per Home Assistant config entry (account)**, not per device. State is subscription `status` (`trialing`, `active`, `canceled`, …, or steady states `none`, `unknown`, `forbidden`). Attributes include `plan_code`, `tier`, `interval`, `currency`, `amount_minor`, period dates, `remaining_seconds`, `is_trial`, `cancel_at_period_end`, `source`, plus `features` and `limits` maps when present. |
| `binary_sensor` | `connectivity` | `online` → on, `offline` → off, `unknown` → unavailable |
| `switch` | `power` | `turn_on` / `turn_off` → `set-mode` with idempotency key; refresh after `202`, no optimistic state |
| `select` | `scene` | Scene titles as options; empty `activeSceneIds` → no selection; `select_option` → `apply-scene` only |
| `button` | `reboot` | `press` → reboot action with idempotency key |

The coordinator polls `GET /v1/devices/{id}/summary` and `GET /v1/devices/{id}/scenes` per device (bounded concurrency). Dynamic discovery adds entities when new devices appear.

### Account subscription

Subscriptions are **account-level** (one per Mitipi user). The integration calls `GET /v1/subscription` on each coordinator poll and exposes a single `sensor.*_account_subscription` entity on the config entry, even when multiple Kevin devices are linked.

Non-error steady states:

| State | Meaning |
| ----- | ------- |
| `none` / `no_subscription` | No subscription record for the account. |
| `unknown` / `not_configured` | Billing integration disabled in Kevin API configuration. |
| `forbidden` / `subscription_read_forbidden` | Read denied (HTTP 403). The entity stays **available** with an explanatory state; this is **not** an auth failure and does not trigger reauth. |

**Live limitation:** the federated AWS role used by Kevin API may not yet have DynamoDB read access for subscriptions. When that happens you will see the `forbidden` state until infrastructure permissions are granted—the integration surfaces this honestly and does not fabricate plan or expiry data.

## Kevin Presence Lovelace card (bundled)

Version **0.3.0** ships `kevin-presence-card.js` (URL includes the integration version for cache busting). After the integration loads, Home Assistant registers the script automatically—**no manual Lovelace resource entry** is required.

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

Per-device sibling entities (mode, connectivity, firmware, scene, reboot) are resolved via the device registry on the same Kevin device. **Account subscription** is resolved once per config entry (`*_account_subscription`), shared by every Kevin card tied to that integration account.

### Sizes

- **compact** (~112px, card size 2): name, confirmed power, connectivity text, primary command.
- **standard** (~256px, card size 5): adds beacon, full-width power command, scene entry.
- **expanded** (~440px, card size 8): adds firmware, serial, account subscription summary (plan/tier, trial, renewal/expiry, coarse remaining time, cancel-at-period-end), low-emphasis reboot.

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
