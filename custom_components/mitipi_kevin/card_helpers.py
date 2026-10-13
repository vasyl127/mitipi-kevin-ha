"""Shape Kevin API data for the KEVIN® Lovelace card (activity, schedule, preferences)."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta
from typing import Any

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$")
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

ENVIRONMENTS = ("HOME", "BUSINESS", "INDUSTRIAL")
CHARACTERISTICS_BY_ENVIRONMENT: dict[str, tuple[str, ...]] = {
    "HOME": ("kids", "teens", "dogs", "cats"),
    "BUSINESS": ("customersPresent", "callsAndMeetings", "deliveryAndLogistics", "petsAllowed"),
    "INDUSTRIAL": ("heavyMachinery", "manualWorkstations", "forkliftTraffic", "safetyAlerts"),
}
LEVEL_MIN = 0
LEVEL_MAX = 10


def _hours(value: Any) -> float | None:
    if not isinstance(value, str):
        return None
    match = _TIME_RE.match(value.strip())
    if not match:
        return None
    hours, minutes = int(match.group(1)), int(match.group(2))
    seconds = int(match.group(3) or 0)
    total = hours + minutes / 60 + seconds / 3600
    if total < 0 or total > 24:
        return None
    return round(total, 4)


def schedule_windows(
    schedules: Any,
    *,
    today: date | None = None,
) -> list[list[list[float]]]:
    """Map app schedules to seven Monday-first lists of [from, to] hours.

    Only enabled windows count. Weekday codes recur; ISO dates count only inside
    the current ISO week, like the app's schedule editor. A window that ends at or
    before its start continues past midnight into the next day.
    """
    days: list[list[list[float]]] = [[] for _ in range(7)]
    if not isinstance(schedules, list):
        return days
    today = today or datetime.now().date()
    week_start = today - timedelta(days=today.weekday())

    def add(index: int, start: float, end: float) -> None:
        if end > start:
            days[index % 7].append([start, end])

    for entry in schedules:
        if not isinstance(entry, dict) or entry.get("enabled") is False:
            continue
        pattern = entry.get("pattern")
        if not isinstance(pattern, dict):
            pattern = entry
        start = _hours(pattern.get("startTime"))
        end = _hours(pattern.get("endTime"))
        dates = pattern.get("dates")
        if start is None or end is None or not isinstance(dates, list):
            continue
        for raw in dates:
            if not isinstance(raw, str):
                continue
            token = raw.strip()
            if token.lower()[:3] in WEEKDAYS and len(token) <= 9:
                index = WEEKDAYS.index(token.lower()[:3])
            elif _ISO_DATE_RE.match(token):
                try:
                    day = date.fromisoformat(token)
                except ValueError:
                    continue
                if not week_start <= day < week_start + timedelta(days=7):
                    continue
                index = day.weekday()
            else:
                continue
            if end > start:
                add(index, start, end)
            else:
                add(index, start, 24.0)
                add(index + 1, 0.0, end)

    for day_windows in days:
        day_windows.sort(key=lambda w: w[0])
    return days


def weekly_hours(windows: list[list[list[float]]]) -> float:
    """Total scheduled Presence hours in the week."""
    return round(sum(end - start for day in windows for start, end in day), 2)


def format_activity_id(activity_id: str) -> str:
    """Prettify a raw activity id like the Mitipi app: onb-cozy_time -> Cozy Time."""
    raw = activity_id.strip()
    raw = re.sub(r"^onb[-_:]?", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"[_:]+", "-", raw)
    words = [w for w in (part.strip() for part in raw.split("-")) if w]
    return " ".join(w[:1].upper() + w[1:] for w in words)


def epoch_to_iso(value: Any) -> str | None:
    """Epoch seconds or milliseconds to an ISO 8601 UTC string."""
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
        return None
    seconds = value / 1000 if value > 1e12 else value
    try:
        return datetime.fromtimestamp(seconds, tz=UTC).isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def activity_from_summary(summary: dict[str, Any] | None) -> dict[str, Any] | None:
    """Current activity from a summary payload ({id,title,group,since})."""
    if not summary:
        return None
    activity = summary.get("activity")
    if not isinstance(activity, dict):
        return None
    activity_id = activity.get("id")
    title = activity.get("title")
    if not isinstance(title, str) or not title.strip():
        if not isinstance(activity_id, str) or not activity_id.strip():
            return None
        title = format_activity_id(activity_id)
    out: dict[str, Any] = {"title": title.strip()[:255]}
    if isinstance(activity_id, str) and activity_id.strip():
        out["id"] = activity_id.strip()[:128]
    group = activity.get("group")
    if isinstance(group, str) and group.strip():
        out["group"] = group.strip()[:255]
    since = epoch_to_iso(activity.get("since"))
    if since:
        out["since"] = since
    return out


def activity_from_state(state: dict[str, Any] | None) -> dict[str, Any] | None:
    """Fallback current activity from a normalized /state payload."""
    if not state:
        return None
    reported = state.get("reported")
    activity = reported.get("activity") if isinstance(reported, dict) else None
    if not isinstance(activity, dict):
        return None
    current = activity.get("current")
    activity_id = None
    name = None
    if isinstance(current, dict):
        activity_id = current.get("id")
        name = current.get("name")
    if not activity_id and isinstance(activity.get("currentActivity"), str):
        activity_id = activity["currentActivity"]
    if not isinstance(activity_id, str) or not activity_id.strip():
        return None
    title = name or activity.get("assetName") or format_activity_id(activity_id)
    out: dict[str, Any] = {"id": activity_id.strip()[:128], "title": str(title)[:255]}
    since = epoch_to_iso(state.get("activitySince"))
    if since:
        out["since"] = since
    return out


def normalize_preferences(payload: Any) -> dict[str, Any] | None:
    """Allow-listed account preferences from GET/PATCH /v1/preferences, or None."""
    if not isinstance(payload, dict) or payload.get("status") != "configured":
        return None
    prefs = payload.get("preferences")
    if not isinstance(prefs, dict):
        return None
    environment = prefs.get("environment")
    if environment not in ENVIRONMENTS:
        return None
    raw_chars = prefs.get("characteristics")
    if not isinstance(raw_chars, dict):
        raw_chars = {}
    characteristics = {
        key: raw_chars.get(key) is True for key in CHARACTERISTICS_BY_ENVIRONMENT[environment]
    }
    out: dict[str, Any] = {"environment": environment, "characteristics": characteristics}
    for api_key, attr in (("occupancyLevel", "occupancy_level"), ("energyLevel", "energy_level")):
        value = prefs.get(api_key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            out[attr] = max(LEVEL_MIN, min(LEVEL_MAX, float(value)))
    locale = prefs.get("locale")
    if isinstance(locale, str) and locale.strip():
        out["locale"] = locale.strip()[:16]
    updated = epoch_to_iso(prefs.get("updatedAt"))
    if updated:
        out["updated_at"] = updated
    return out
