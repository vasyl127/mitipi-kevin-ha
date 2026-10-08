"""Constants for the Mitipi Kevin integration."""

from datetime import timedelta

DOMAIN = "mitipi_kevin"
INTEGRATION_VERSION = "0.2.1"

# Single approved Kevin API host; not user-configurable.
KEVIN_API_BASE_URL = "https://mitipi.marmash.dev/api"

# Legacy config-entry key (removed on migration from version 1).
CONF_BASE_URL = "base_url"

CONF_EMAIL = "email"
CONF_PASSWORD = "password"

HEADER_ID_TOKEN = "x-auth0-id-token"
HEADER_IDEMPOTENCY = "Idempotency-Key"

UPDATE_INTERVAL = timedelta(seconds=60)
PARALLEL_UPDATES = 5

MODE_ON = "ON"
MODE_STAND_BY = "STAND_BY"

PLATFORMS = ["sensor", "binary_sensor", "switch", "select", "button"]
