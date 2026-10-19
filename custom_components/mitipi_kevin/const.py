"""Constants for the Mitipi Kevin integration."""

from datetime import timedelta

DOMAIN = "mitipi_kevin"
INTEGRATION_VERSION = "0.5.2"

# Single approved Kevin API host; not user-configurable.
KEVIN_API_BASE_URL = "https://mitipi.marmash.dev/api"

# Legacy config-entry key (removed on migration from version 1).
CONF_BASE_URL = "base_url"

CONF_EMAIL = "email"
CONF_PASSWORD = "password"

HEADER_ID_TOKEN = "x-auth0-id-token"
HEADER_IDEMPOTENCY = "Idempotency-Key"
# Names this integration release to the Kevin API (shown in the admin panel).
HEADER_CLIENT = "x-mitipi-kevin-client"
CLIENT_ID = f"{DOMAIN}/{INTEGRATION_VERSION}"

UPDATE_INTERVAL = timedelta(seconds=60)
PARALLEL_UPDATES = 5

# After /summary fails, retry it every N coordinator polls (not every poll).
SUMMARY_RETRY_INTERVAL_POLLS = 10

# Account preferences change rarely; read them every N polls once known.
PREFERENCES_POLL_EVERY = 5

# The scene catalog changes rarely and the summary already carries the active scenes.
SCENES_POLL_EVERY = 5

# A Kevin keeps its last known state through this many failed polls in a row before
# its entities turn unavailable (one flaky API call must not blank the card).
STALE_POLLS_ALLOWED = 3

# After a mode change, poll only that Kevin's summary until it reports the new mode.
MODE_CONFIRM_INTERVAL = 1.5  # seconds between summary reads
MODE_CONFIRM_TIMEOUT = 30.0  # give up after this long; the regular poll takes over

SERVICE_SET_PREFERENCES = "set_preferences"

MODE_ON = "ON"
MODE_STAND_BY = "STAND_BY"

PLATFORMS = ["sensor", "binary_sensor", "switch", "select", "button"]
