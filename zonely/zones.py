"""Timezone catalogue, straight from the standard library."""

from datetime import datetime
from zoneinfo import ZoneInfo, available_timezones

# Shown as one-click chips. Everything else is reachable via the full picker.
POPULAR = [
    ("San Francisco", "America/Los_Angeles"),
    ("Denver", "America/Denver"),
    ("Chicago", "America/Chicago"),
    ("New York", "America/New_York"),
    ("São Paulo", "America/Sao_Paulo"),
    ("London", "Europe/London"),
    ("Lisbon", "Europe/Lisbon"),
    ("Berlin", "Europe/Berlin"),
    ("Warsaw", "Europe/Warsaw"),
    ("Lagos", "Africa/Lagos"),
    ("Cairo", "Africa/Cairo"),
    ("Nairobi", "Africa/Nairobi"),
    ("Dubai", "Asia/Dubai"),
    ("Bengaluru", "Asia/Kolkata"),
    ("Singapore", "Asia/Singapore"),
    ("Shanghai", "Asia/Shanghai"),
    ("Tokyo", "Asia/Tokyo"),
    ("Sydney", "Australia/Sydney"),
    ("Auckland", "Pacific/Auckland"),
]


def all_zones() -> list[str]:
    return sorted(available_timezones())


def offset_label(tz: str, when: datetime | None = None) -> str:
    when = when or datetime.now()
    offset = ZoneInfo(tz).utcoffset(when.replace(tzinfo=None))
    hours = offset.total_seconds() / 3600 if offset else 0
    return f"UTC{hours:+g}"
