"""Deployment target of this build: which Kevin API it talks to and where it is released.

The integration ships from two repositories built from the same code:

- github.com/vasyl127/mitipi-kevin-ha   -> stage Kevin API (testing)
- github.com/teamvoydev/mitipi-kevin    -> production Kevin API

The values below, the links in manifest.json and hacs.json, the HACS URL in README.md and
the card's documentationURL are the only differences between them;
tests/test_environment.py keeps them consistent.
"""

ENVIRONMENT = "stage"
KEVIN_API_BASE_URL = "https://stage-mitipi-api.teamvoy.com/api"
GITHUB_REPOSITORY = "vasyl127/mitipi-kevin-ha"
