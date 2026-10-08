"""Constants for the Mitipi Kevin integration."""

from datetime import timedelta

DOMAIN = "mitipi_kevin"

DEFAULT_BASE_URL = "https://mitipi.marmash.dev/api"

CONF_BASE_URL = "base_url"
CONF_EMAIL = "email"
CONF_PASSWORD = "password"

HEADER_ID_TOKEN = "x-auth0-id-token"
HEADER_IDEMPOTENCY = "Idempotency-Key"

UPDATE_INTERVAL = timedelta(seconds=60)
PARALLEL_UPDATES = 5

MODE_ON = "ON"
MODE_STAND_BY = "STAND_BY"

ALLOWED_API_PATH_PREFIXES = (
    "/v1/auth/login",
    "/v1/devices",
)

PLATFORMS = ["sensor", "binary_sensor", "switch"]
