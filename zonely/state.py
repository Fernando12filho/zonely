"""Team state lives in the URL, not a database.

That keeps the whole app stateless -- no signup, no storage, no privacy
surface -- and makes every plan a link you can paste into Slack.
"""

from __future__ import annotations

import base64
import json
from zoneinfo import available_timezones

from .scoring import Member

_ZONES = available_timezones()

# Short keys keep the URL manageable for a team of eight.
_FIELDS = [
    ("name", "n", str),
    ("tz", "z", str),
    ("work_start", "a", float),
    ("work_end", "b", float),
    ("sleep_start", "c", float),
    ("sleep_end", "d", float),
    ("burden", "u", float),
]

MAX_MEMBERS = 12


_DEFAULTS = Member(name="", tz="UTC")


def encode(members: list[Member]) -> str:
    """Only non-default fields go in, so a typical link stays short."""
    rows = []
    for m in members:
        row = {}
        for attr, key, _ in _FIELDS:
            value = getattr(m, attr)
            if attr != "tz" and value == getattr(_DEFAULTS, attr):
                continue
            row[key] = round(value, 2) if isinstance(value, float) else value
        rows.append(row)
    raw = json.dumps(rows, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode(token: str) -> list[Member]:
    """Parse a share token. Never raises -- a mangled link yields an empty team."""
    if not token:
        return []
    try:
        padded = token + "=" * (-len(token) % 4)
        rows = json.loads(base64.urlsafe_b64decode(padded))
    except Exception:
        return []
    if not isinstance(rows, list):
        return []
    return _members_from(rows[:MAX_MEMBERS], key=lambda f: f[1])


def from_payload(rows: list[dict]) -> list[Member]:
    """Parse the JSON the browser posts, which uses the long field names."""
    if not isinstance(rows, list):
        return []
    return _members_from(rows[:MAX_MEMBERS], key=lambda f: f[0])


def _members_from(rows, key) -> list[Member]:
    members = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        tz = str(row.get(key(("tz", "z", str))) or "").strip()
        if tz not in _ZONES:
            continue  # unknown zone would blow up ZoneInfo later
        kwargs = {}
        for field in _FIELDS:
            attr, _, cast = field
            if attr == "tz":
                continue
            value = row.get(key(field))
            if value is None or value == "":
                continue
            try:
                kwargs[attr] = cast(value)
            except (TypeError, ValueError):
                continue
        name = str(kwargs.pop("name", "") or "").strip()[:24] or tz.split("/")[-1].replace("_", " ")
        for bound in ("work_start", "work_end", "sleep_start", "sleep_end"):
            if bound in kwargs:
                kwargs[bound] = min(24.0, max(0.0, kwargs[bound]))
        if "burden" in kwargs:
            kwargs["burden"] = max(0.0, min(100_000.0, kwargs["burden"]))
        members.append(Member(name=name, tz=tz, **kwargs))
    return members
