# Mitipi Kevin for Home Assistant (HACS)

Production-oriented custom integration that connects Home Assistant to **Mitipi Kevin** through the Kevin HTTP API only. Home Assistant never talks to Auth0, Cognito, AWS Lambda, MQTT, or legacy AWS routes directly—credentials are exchanged once with `POST /v1/auth/login`, and all device traffic uses Bearer + `x-auth0-id-token` headers on Kevin API paths.

## HACS installation

1. Add this repository as a [custom repository](https://hacs.xyz/docs/faq/custom_repositories/) in HACS (Integration).
2. Install **Mitipi Kevin** and restart Home Assistant.
3. Go to **Settings → Devices & services → Add integration** and search for **Mitipi Kevin**.

Alternatively, copy `custom_components/mitipi_kevin` into your Home Assistant `config/custom_components/` directory and restart.

## Configuration flow

The config flow collects:

| Field | Description |
| ----- | ----------- |
| **Kevin API base URL** | Default `https://mitipi.marmash.dev/api` |
| **Email** | Mitipi app user email |
| **Password** | Mitipi app user password |

On submit, the integration validates credentials by logging in and calling `GET /v1/devices`. Access and ID tokens are kept **in memory only** and are not written to the config entry or logs.

If the API returns `401` during normal operation, Home Assistant starts a **re-authentication** flow that asks only for email and password while preserving the configured base URL.

Use the integration's **Reconfigure** action to change the Kevin API base URL. The replacement connection is validated with the existing credentials before Home Assistant saves it and reloads the entry.

## Architecture

- **Hub integration** (`integration_type: hub`) with `iot_class: cloud_polling`.
- **`KevinApiClient`**: async HTTP via Home Assistant’s shared `aiohttp` session; one automatic re-login on `401`, then failure.
- **`MitipiKevinCoordinator`**: polls `GET /v1/devices`, then fetches each device’s `state` and `capabilities` with bounded parallelism.
- **Dynamic discovery**: when a new device appears on a later poll, platform entities are added via a coordinator listener (no config reload).

### Security posture

- The password is retained in Home Assistant's config-entry storage because the API requires email/password re-login. Home Assistant operators must protect `.storage`, backups, and host access; this integration does not claim storage encryption.
- Access and ID tokens live in memory only. Passwords, tokens, and authorization headers are never logged.
- API error bodies are not surfaced to users in the UI or logs.
- Only documented Kevin API routes under `/v1/auth/login` and `/v1/devices/...` are used.

## Entity model

Each registry device gets three entities (stable `unique_id` = `{apiDeviceId}_{role}`):

| Platform | Entity | Behavior |
| -------- | ------ | -------- |
| `sensor` | Mode | `state.reported.mode` (`ON` / `STAND_BY`); unavailable when offline/unknown |
| `binary_sensor` | Connectivity | `availability` `online` → on, `offline` → off, `unknown` → unavailable |
| `switch` | Power | `turn_on` → `POST .../actions/set-mode` `{mode:"ON"}`; `turn_off` → `{mode:"STAND_BY"}` with UUID `Idempotency-Key`; `202` triggers refresh but does not optimistically flip reported state |

Device names prefer `kevinDeviceId` when present. Device identifiers: `(mitipi_kevin, {apiDeviceId})`.

## Development

Requires Python 3.12+.

```bash
pip install "homeassistant==2024.12.5" pytest pytest-asyncio pytest-homeassistant-custom-component ruff aioresponses
ruff check .
pytest
```

**Home Assistant compatibility:** developed and tested against Home Assistant **2024.12.5** (minimum declared in `hacs.json`: **2024.4.0** for `ConfigEntry.runtime_data`).

## License

MIT — see [LICENSE](LICENSE).
