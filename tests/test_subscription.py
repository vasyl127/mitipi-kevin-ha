"""Account-level subscription client and entity tests."""

from __future__ import annotations

import pytest
from aioresponses import aioresponses
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mitipi_kevin.api import KevinApiClient, KevinAuthError
from custom_components.mitipi_kevin.const import CONF_EMAIL, CONF_PASSWORD, DOMAIN
from custom_components.mitipi_kevin.subscription_helpers import (
    parse_account_subscription,
    subscription_state_attributes,
)
from tests.conftest import (
    DEVICE_ONE,
    DEVICE_TWO,
    TEST_BASE_URL,
    TEST_EMAIL,
    TEST_PASSWORD,
    KevinApiStub,
)


def test_parse_trialing_subscription() -> None:
    """Full subscription object maps to normalized dict."""
    payload = {
        "subscription": {
            "status": "trialing",
            "planCode": "kevin_plus",
            "tier": "plus",
            "interval": "month",
            "currency": "eur",
            "amountMinor": 7900,
            "isTrial": True,
            "remainingSeconds": 86400,
            "source": "stripe",
            "features": {"scenes": True},
            "limits": {"devices": 5},
        }
    }
    parsed = parse_account_subscription(200, payload)
    assert parsed["status"] == "trialing"
    attrs = subscription_state_attributes(parsed)
    assert attrs["plan_code"] == "kevin_plus"
    assert attrs["amount_minor"] == 7900
    assert attrs["is_trial"] is True
    assert attrs["features"]["scenes"] is True


def test_parse_none_and_not_configured() -> None:
    """Non-success steady states are not errors."""
    none = parse_account_subscription(200, {"status": "none", "source": "no_subscription"})
    assert none["status"] == "none"
    unknown = parse_account_subscription(200, {"status": "unknown", "source": "not_configured"})
    assert unknown["source"] == "not_configured"


def test_parse_forbidden_distinct_from_401() -> None:
    """403 subscription_read_forbidden is a degraded state, not auth failure."""
    parsed = parse_account_subscription(
        403, {"code": "subscription_read_forbidden", "message": "denied"}
    )
    assert parsed["status"] == "forbidden"
    with pytest.raises(KevinAuthError):
        parse_account_subscription(401, {})


def test_remaining_seconds_clamped_in_attributes() -> None:
    """Expired subscriptions may report zero remaining seconds from the API."""
    parsed = parse_account_subscription(
        200,
        {
            "subscription": {
                "status": "canceled",
                "remainingSeconds": 0,
                "cancelAtPeriodEnd": True,
                "expiresAt": "2020-01-01T00:00:00Z",
            }
        },
    )
    attrs = subscription_state_attributes(parsed)
    assert parsed["status"] == "canceled"
    assert attrs["remaining_seconds"] == 0
    assert attrs["cancel_at_period_end"] is True


def test_billing_identifiers_stripped_from_attributes() -> None:
    """Fabricated billing ids must not appear on entity attributes."""
    parsed = parse_account_subscription(
        200,
        {
            "subscription": {
                "status": "active",
                "planCode": "pro",
                "stripeCustomerId": "cus_FABRICATED123",
                "customerId": "cust_FABRICATED",
            }
        },
    )
    attrs = subscription_state_attributes(parsed)
    assert "stripeCustomerId" not in attrs
    assert "customerId" not in attrs
    assert "stripe" not in str(attrs).lower()


async def test_account_subscription_entity_single_for_multi_device(
    hass: HomeAssistant, kevin_stub: KevinApiStub
) -> None:
    """One account subscription entity regardless of device count."""
    kevin_stub.set_devices([DEVICE_ONE, DEVICE_TWO])
    kevin_stub.account_subscription = {
        "subscription": {"status": "active", "planCode": "standard", "source": "stripe"}
    }
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_EMAIL: TEST_EMAIL, CONF_PASSWORD: TEST_PASSWORD},
    )
    entry.add_to_hass(hass)
    with aioresponses() as mock:
        kevin_stub.apply(mock)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    registry = er.async_get(hass)
    entities = er.async_entries_for_config_entry(registry, entry.entry_id)
    subs = [e for e in entities if e.unique_id.endswith("_account_subscription")]
    assert len(subs) == 1
    state = hass.states.get(subs[0].entity_id)
    assert state.state == "active"
    assert state.attributes.get("plan_code") == "standard"


async def test_forbidden_subscription_entity_stays_available(
    hass: HomeAssistant, kevin_stub: KevinApiStub
) -> None:
    """Forbidden subscription read does not fail the config entry or hide the entity."""
    kevin_stub.set_devices([DEVICE_ONE])
    kevin_stub.account_subscription_status = 403
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_EMAIL: TEST_EMAIL, CONF_PASSWORD: TEST_PASSWORD},
    )
    entry.add_to_hass(hass)
    with aioresponses() as mock:
        kevin_stub.apply(mock)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    registry = er.async_get(hass)
    entries = er.async_entries_for_config_entry(registry, entry.entry_id)
    sub = next(e for e in entries if "account_subscription" in e.unique_id)
    state = hass.states.get(sub.entity_id)
    assert state.state == "forbidden"
    assert state.state != "unavailable"
    assert state.attributes.get("source") == "subscription_read_forbidden"


async def test_get_account_subscription_client(hass: HomeAssistant) -> None:
    """Client fetches /v1/subscription with normalized body."""
    with aioresponses() as mock:
        mock.post(
            f"{TEST_BASE_URL}/v1/auth/login",
            status=200,
            payload={"accessToken": "access-token", "idToken": "id-token"},
        )
        mock.get(
            f"{TEST_BASE_URL}/v1/subscription",
            status=200,
            payload={"status": "none", "source": "no_subscription"},
        )
        client = KevinApiClient(
            async_get_clientsession(hass), TEST_BASE_URL, TEST_EMAIL, TEST_PASSWORD
        )
        await client.login()
        sub = await client.get_account_subscription()
    assert sub["status"] == "none"
