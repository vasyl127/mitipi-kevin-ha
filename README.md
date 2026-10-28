<p align="center"><img src="docs/assets/logo.png" alt="Mitipi Kevin" width="128" height="128"></p>

# Mitipi Kevin for Home Assistant (HACS)

> **Stage build.** This repository talks to the **stage** Kevin API (`https://stage-mitipi-api.teamvoy.com/api`) and is meant for testing. The production integration is [teamvoydev/mitipi-kevin](https://github.com/teamvoydev/mitipi-kevin).

Production-oriented custom integration that connects Home Assistant to **Mitipi Kevin** through the Kevin HTTP API only. Home Assistant never talks to Auth0, Cognito, AWS Lambda, MQTT, or legacy AWS routes directly—credentials are exchanged once with `POST /v1/auth/login`, and all device traffic uses Bearer + `x-auth0-id-token` headers on Kevin API paths.

## HACS installation

1. In HACS → **Custom repositories**, add `https://github.com/vasyl127/mitipi-kevin-ha` as category **Integration**.
2. Install **Mitipi Kevin (Stage)** and restart Home Assistant.
3. Go to **Settings → Devices & services → Add integration** and search for **Mitipi Kevin**.

Alternatively, copy `custom_components/mitipi_kevin` into your Home Assistant `config/custom_components/` directory and restart.

## Updates

HACS re-reads custom repositories only every 48 hours, counted from Home Assistant's start, so a new release can stay invisible for days. The integration therefore checks the latest GitHub release itself, two minutes after start and then every 6 hours. When a newer version exists it asks HACS to refresh this repository, and the update appears under **Settings → Updates** with an Install button. If HACS is not available, a notice in **Settings → Repairs** links to the release instead.

On Home Assistant 2026.3 and later, the integration also points the HACS update entity's picture at this integration's own brand icon (`/api/brands/integration/mitipi_kevin/icon.png`), because HACS still uses the legacy [brands CDN](https://github.com/hacs/integration/issues/5171) where custom integrations show a grey placeholder. If you set `entity_picture` for that update entity under `homeassistant.customize`, your value is kept and is not overwritten.

## Configuration flow

All traffic uses the fixed Kevin API base URL of this build (`https://stage-mitipi-api.teamvoy.com/api`, set in `custom_components/mitipi_kevin/environment.py`); the host is not user-configurable.

Adding the integration opens the **Sign in with Mitipi** page in a new browser tab. Sign in there with Google, Apple or your KEVIN® e-mail and password; the tab then returns to Home Assistant through My Home Assistant and the entry is created. Home Assistant stores the account's tokens (refreshed automatically) and never sees a password. This needs the `my` integration, which is part of `default_config`. Which of Google, Apple and e-mail the page offers is set on the Kevin API.

Entries created with e-mail and password by releases before v0.7.0 keep working with their stored password. When the API rejects the stored credentials (password changed or tokens revoked), Home Assistant starts **re-authentication**: it opens the same Mitipi sign-in page and updates the existing entry, which from then on uses tokens instead of the password. Signing in with a different KEVIN® account than the entry belongs to is refused.

## Upgrading, downgrading and removal

- **Upgrade:** install the new release from **Settings → Updates** (or HACS) and restart Home Assistant. Entity IDs and `unique_id`s stay the same across releases, so dashboards and automations keep working.
- **Downgrade:** in HACS open **Mitipi Kevin → ⋮ → Redownload**, pick the earlier version and restart. E-mail and password entries work with every published release (v0.2.0 and later), so no re-setup is needed. Entries created with **Sign in with Mitipi** need v0.7.0 or later; after downgrading below it, remove them and add the account again with e-mail and password.
- **Removal:** delete the integration under **Settings → Devices & services**, then remove it in HACS and restart. Removing the entry deletes its devices and entities from Home Assistant; nothing changes on the Kevin devices or in the Mitipi account.

## Diagnostics

**Settings → Devices & services → Mitipi Kevin → ⋮ → Download diagnostics** saves a JSON file to attach to a support request. It contains the integration version and build environment, the Kevin API it talks to, poll health (last update result, failed polls in a row, devices read through the `/state` fallback, preferences state), the subscription plan and status, and per device its API id, availability, mode, firmware, scene counts and stale polls.

It also says which sign-in method the entry uses. It never contains the e-mail address, the password, tokens or device names: the entry title, credentials and the stored tokens of a Sign in with Mitipi entry are replaced with `**REDACTED**`.

## Known limitations

- **Cloud polling.** State is read every 60 seconds (scenes every fifth poll), so a change made in the Mitipi app or on the device shows up within about a minute. A mode change made from Home Assistant settles faster: the integration re-reads that Kevin every 1.5 s for up to 30 s.
- **Internet and the Kevin API are required.** There is no local control. During an outage entities keep their last state for 3 polls, then become unavailable.
- **Commands need the Kevin online.** Power, scene and reboot actions are accepted by the API and confirmed by the next read; an offline device does not change state.
- **Controls exposed:** power, scene and reboot per device, plus account preferences through the `mitipi_kevin.set_preferences` service. There is no separate light entity.
- **Credential storage.** Sign in with Mitipi stores no password, only the account's access, ID and refresh tokens in the config entry (Home Assistant's `.storage`). E-mail and password entries from releases before v0.7.0 keep the password there until their next re-authentication.
- **Sign in with Mitipi needs a browser and My Home Assistant.** The sign-in returns through `my.home-assistant.io`; installations without the `my` integration cannot add the account.
- **One build, one API.** This build always talks to the API named at the top of this README; stage and production are separate repositories and are installed separately.
- **One entry per Kevin account.** Adding the same account twice is refused.

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
