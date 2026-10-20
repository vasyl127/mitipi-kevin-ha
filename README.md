<p align="center"><img src="docs/assets/logo.png" alt="Mitipi Kevin" width="128" height="128"></p>

# Mitipi Kevin for Home Assistant (HACS)

Production-oriented custom integration that connects Home Assistant to **Mitipi Kevin** through the Kevin HTTP API only. Home Assistant never talks to Auth0, Cognito, AWS Lambda, MQTT, or legacy AWS routes directly—credentials are exchanged once with `POST /v1/auth/login`, and all device traffic uses Bearer + `x-auth0-id-token` headers on Kevin API paths.

## HACS installation

1. In HACS → **Custom repositories**, add `https://github.com/vasyl127/mitipi-kevin-ha` as category **Integration**.
2. Install **Mitipi Kevin** and restart Home Assistant.
3. Go to **Settings → Devices & services → Add integration** and search for **Mitipi Kevin**.

Alternatively, copy `custom_components/mitipi_kevin` into your Home Assistant `config/custom_components/` directory and restart.

## Updates

HACS re-reads custom repositories only every 48 hours, counted from Home Assistant's start, so a new release can stay invisible for days. The integration therefore checks the latest GitHub release itself, two minutes after start and then every 6 hours. When a newer version exists it asks HACS to refresh this repository, and the update appears under **Settings → Updates** with an Install button. If HACS is not available, a notice in **Settings → Repairs** links to the release instead.

On Home Assistant 2026.3 and later, the integration also points the HACS update entity's picture at this integration's own brand icon (`/api/brands/integration/mitipi_kevin/icon.png`), because HACS still uses the legacy [brands CDN](https://github.com/hacs/integration/issues/5171) where custom integrations show a grey placeholder. If you set `entity_picture` for that update entity under `homeassistant.customize`, your value is kept and is not overwritten.

## Configuration flow

The config flow collects **email** and **password** only. All traffic uses the fixed Kevin API base URL (`https://mitipi.marmash.dev/api`); the host is not user-configurable.

On submit, the integration validates credentials by logging in and calling `GET /v1/devices`. Access and ID tokens are kept **in memory only** and are not written to the config entry or logs.

If the API returns `401` during normal operation, Home Assistant starts a **re-authentication** flow that asks only for email and password.

## Entity model

Each Kevin device exposes entities with stable `unique_id` = `{apiDeviceId}_{role}`:

| Platform | Role | Behavior |
| -------- | ---- | -------- |
| `sensor` | `mode` | Reported mode (`ON` / `STAND_BY`); unavailable when offline/unknown |
| `sensor` | `firmware` | Firmware version from `/summary`, or from `/state` / `/capabilities` when summary is unavailable |
| `sensor` | `account_subscription` | **One per Home Assistant config entry (account)**, not per device. State is subscription `status` (`trialing`, `active`, `canceled`, …, or steady states `none`, `unknown`, `forbidden`). Attributes include `plan_code`, `tier`, `interval`, `currency`, `amount_minor`, period dates, `remaining_seconds`, `is_trial`, `cancel_at_period_end`, `source`, plus `features` and `limits` maps when present. |
| `binary_sensor` | `connectivity` | `online` → on, `offline` → off, `unknown` → unknown; keeps a `last_seen` attribute with the newest known report |
| `switch` | `power` | `turn_on` / `turn_off` → `set-mode` with idempotency key; refresh after `202`, no optimistic state |
| `select` | `scene` | Scene titles as options; empty `activeSceneIds` → no selection; `select_option` → `apply-scene` only |
| `button` | `reboot` | `press` → reboot action with idempotency key |

The coordinator polls `GET /v1/subscription` once per account, then per device prefers `GET /v1/devices/{id}/summary` plus `GET /v1/devices/{id}/scenes`. If `/summary` fails (for example HTTP 403 while billing read permissions are missing on the deployed API), it falls back to `GET /v1/devices/{id}/state` and `GET /v1/devices/{id}/capabilities` so Power, Mode, Connectivity, Firmware, and Scene keep working. After a summary failure the integration avoids hammering `/summary` on every poll and retries occasionally. Subscription errors never mark device entities unavailable. Dynamic discovery adds entities when new devices appear.

Scenes are read on the first poll and then every fifth poll; a failed `/scenes` request keeps the previous catalog and never affects power or connectivity. When one Kevin's poll fails, or the whole API is briefly unreachable, its entities keep the last known state for up to 3 polls before turning unavailable. After a mode change the integration reads only that Kevin's `/summary` every 1.5 s until it reports the new mode (up to 30 s), so the card settles a few seconds after the device does instead of waiting for the next one-minute poll. While the change is pending the card shows a loading animation.

### Account subscription

Subscriptions are **account-level** (one per Mitipi user). The integration calls `GET /v1/subscription` on each coordinator poll and exposes a single `sensor.*_account_subscription` entity on the config entry, even when multiple Kevin devices are linked.

Non-error steady states:

| State | Meaning |
| ----- | ------- |
| `none` / `no_subscription` | No subscription record for the account. |
| `unknown` / `not_configured` | Billing integration disabled in Kevin API configuration. |
| `forbidden` / `subscription_read_forbidden` / `read_forbidden` | Read denied or not permitted. The entity stays **available** with an explanatory state; this is **not** an auth failure and does not trigger reauth. |
| `unknown` / `read_error` | Transient or upstream read failure; device entities remain available. |

**Live limitation:** the federated AWS role used by Kevin API may not yet have DynamoDB read access for subscriptions. When that happens you will see the `forbidden` state until infrastructure permissions are granted—the integration surfaces this honestly and does not fabricate plan or expiry data.

## Kevin Presence Lovelace card (bundled)

The integration ships `kevin-presence-card.js` and registers it with the frontend automatically (the URL includes the integration version for cache busting), so **no manual Lovelace resource entry** is required. The design follows `docs/card/prototypes/kevin-ha-card-v7-ha-dark.html` and reads every colour from the active Home Assistant theme.

```yaml
type: custom:kevin-presence-card
entity: switch.kevin_z40189_power
variant: standard
```

### Card configuration

| Key | Required | Values | Default |
| --- | -------- | ------ | ------- |
| `entity` | yes | Kevin **power** switch `entity_id` | — |
| `variant` | no | `minimal`, `standard`, `full` | `standard` |
| `name` | no | Text shown instead of the device name | device name |

Older dashboards keep working: `layout: compact` and `size: compact` map to `minimal`, `size: expanded` and `layout: full` map to `full`. Saving the card in the editor rewrites the config with `variant`.

### Variants

- **minimal** — the Home Assistant tile, 6 × 1 in a sections grid. The icon circle switches On and Standby, the row opens more info, and a dot on the icon flags a trial, an ending or an expired subscription.
- **standard** — the everyday card (12 columns): a window with KEVIN on a shelf and the day-night switch, now playing, the subscription ring, the week schedule, preferences behind a gear, firmware and reboot.
- **full** — the same card unfolded: hours per day and an hour ruler on the schedule, the preferences editor always open, and a device block with serial, firmware, state and reboot.

Standard and full reflow by their own width: one column under 560 px, the window on the left from 560 px, three body columns from 860 px.

Mode changes are not optimistic: the card shows a pending state until the switch reports the requested mode. Reboot goes through a confirmation dialog and uses `button.press`; preferences are saved with `mitipi_kevin.set_preferences`.

### Icons

- `custom_components/mitipi_kevin/brand/` holds the integration icon and logo shown by Home Assistant and HACS (`icon.png`, `icon@2x.png`, `logo.png`, `logo@2x.png`). They are cut out of the product photo.
- `docs/assets/icons/` holds the full icon set from the design:
  - `kevin-mono.svg`: the one-path glyph traced from the photo, drawn in `currentColor`. The card header and the tile use it.
  - `kevin-color.svg`: a flat two-tone version of the traced outline.
  - `kevin-tile.svg`: the glyph on a Mitipi navy tile.
  - PNG renders at 256 and 512 px: `kevin-photo-*.png`, `kevin-color-*.png`, `kevin-tile-*.png`.

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
