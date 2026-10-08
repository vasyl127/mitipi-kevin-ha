"""Normalize Kevin account subscription API payloads for entities."""

from __future__ import annotations

from typing import Any

from .api import KevinApiError, KevinAuthError, KevinConnectionError

_BILLING_KEY_FRAGMENTS = (
    "customerid",
    "stripe",
    "subscriptionid",
    "priceid",
    "invoiceid",
    "paymentmethod",
    "auth0",
    "email",
)

_SCALAR_ATTR_MAP = (
    ("planCode", "plan_code"),
    ("tier", "tier"),
    ("interval", "interval"),
    ("currency", "currency"),
    ("amountMinor", "amount_minor"),
    ("expiresAt", "expires_at"),
    ("currentPeriodStart", "current_period_start"),
    ("currentPeriodEnd", "current_period_end"),
    ("trialEndsAt", "trial_ends_at"),
    ("cancelAtPeriodEnd", "cancel_at_period_end"),
    ("remainingSeconds", "remaining_seconds"),
    ("isTrial", "is_trial"),
    ("source", "source"),
)


def _is_billing_key(key: str) -> bool:
    lowered = key.lower()
    return any(fragment in lowered for fragment in _BILLING_KEY_FRAGMENTS)


def parse_account_subscription(status: int, data: Any) -> dict[str, Any]:
    """Map HTTP status and JSON body to a normalized subscription dict."""
    if status == 401:
        raise KevinAuthError
    if status == 403:
        if isinstance(data, dict) and _error_code(data) == "subscription_read_forbidden":
            return {"status": "forbidden", "source": "subscription_read_forbidden"}
        raise KevinApiError
    if status >= 500:
        raise KevinConnectionError
    if status >= 400:
        raise KevinApiError
    if not isinstance(data, dict):
        raise KevinApiError

    if isinstance(data.get("subscription"), dict):
        return dict(data["subscription"])
    if data.get("status") is not None:
        return {key: value for key, value in data.items() if not _is_billing_key(key)}
    raise KevinApiError


def _error_code(data: dict[str, Any]) -> str | None:
    code = data.get("code") or data.get("error") or data.get("errorCode")
    return str(code) if code is not None else None


def subscription_state_attributes(subscription: dict[str, Any]) -> dict[str, Any]:
    """Build Home Assistant attributes from a normalized subscription dict."""
    attrs: dict[str, Any] = {}
    for api_key, attr_key in _SCALAR_ATTR_MAP:
        if (
            api_key in subscription
            and subscription[api_key] is not None
            and not _is_billing_key(api_key)
        ):
            attrs[attr_key] = subscription[api_key]
    if isinstance(subscription.get("features"), dict):
        attrs["features"] = {
            key: value
            for key, value in subscription["features"].items()
            if not _is_billing_key(key)
        }
    if isinstance(subscription.get("limits"), dict):
        attrs["limits"] = {
            key: value for key, value in subscription["limits"].items() if not _is_billing_key(key)
        }
    return attrs
