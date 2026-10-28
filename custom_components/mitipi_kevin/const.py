"""Constants for the Mitipi Kevin integration."""

from datetime import timedelta

from .environment import KEVIN_API_BASE_URL as ENVIRONMENT_API_BASE_URL

DOMAIN = "mitipi_kevin"
INTEGRATION_VERSION = "0.6.2"

# Single approved Kevin API host for this build (stage or production); not user-configurable.
KEVIN_API_BASE_URL = ENVIRONMENT_API_BASE_URL

# Legacy config-entry key (removed on migration from version 1).
CONF_BASE_URL = "base_url"

CONF_EMAIL = "email"
CONF_PASSWORD = "password"

# How an entry signs in. Absent on e-mail/password entries (the original format).
CONF_AUTH_METHOD = "auth_method"
AUTH_METHOD_OAUTH = "oauth"
CONF_TOKEN = "token"
# Public OAuth client id the Kevin API knows for "Sign in with Mitipi" (PKCE, no secret).
OAUTH_CLIENT_ID = "mitipi-kevin-home-assistant"

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
