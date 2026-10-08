"""Build coordinator device summary payloads from granular API routes."""

from __future__ import annotations

from typing import Any


def build_summary_from_device_routes(
    device: dict[str, Any],
    state: dict[str, Any] | None,
    capabilities: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Synthesize a summary-shaped dict from /state and /capabilities."""
    if not state and not capabilities:
        return None

    summary: dict[str, Any] = {"device": dict(device)}
    availability = _pick_str(state, "availability") or _pick_str(capabilities, "availability")
    if availability is not None:
        summary["availability"] = availability

    mode = _mode_from_state(state)
    if mode is not None:
        summary["mode"] = mode

    firmware = _firmware_from_payloads(state, capabilities)
    if firmware is not None:
        summary["firmwareVersion"] = firmware

    device_block = _device_block(state, capabilities)
    if device_block:
        summary["device"] = {**summary["device"], **device_block}

    return summary


def _pick_str(payload: dict[str, Any] | None, key: str) -> str | None:
    if not payload:
        return None
    value = payload.get(key)
    return str(value) if value is not None else None


def _mode_from_state(state: dict[str, Any] | None) -> str | None:
    if not state:
        return None
    reported = state.get("reported")
    if isinstance(reported, dict) and reported.get("mode") is not None:
        return str(reported["mode"])
    if state.get("mode") is not None:
        return str(state["mode"])
    return None


def _firmware_from_payloads(
    state: dict[str, Any] | None,
    capabilities: dict[str, Any] | None,
) -> str | None:
    for payload in (state, capabilities):
        if not payload:
            continue
        for key in ("firmwareVersion", "firmware_version", "firmware"):
            if payload.get(key) is not None:
                return str(payload[key])
        reported = payload.get("reported")
        if isinstance(reported, dict):
            for key in ("firmwareVersion", "firmware_version", "firmware"):
                if reported.get(key) is not None:
                    return str(reported[key])
    return None


def _device_block(
    state: dict[str, Any] | None,
    capabilities: dict[str, Any] | None,
) -> dict[str, Any]:
    for payload in (state, capabilities):
        if not payload:
            continue
        nested = payload.get("device")
        if isinstance(nested, dict):
            return dict(nested)
    return {}
