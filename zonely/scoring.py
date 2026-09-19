"""The fairness engine.

Given a set of teammates in different timezones, score every possible meeting
slot by how much it hurts -- then rank slots so the pain lands fairly instead of
always on the same person.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, date, time
from zoneinfo import ZoneInfo

# Pain is expressed on a 0-100 scale so the numbers mean something to a human:
#   0    = comfortably inside your working day
#   100  = you are asleep and this meeting wakes you up
SLEEP_PAIN = 100.0
MAX_AWAKE_PAIN = 85.0

# How hard we punish a slot for being lopsided. At 0 we'd optimise pure average
# pain, which happily sacrifices one person forever to keep the mean low.
UNFAIRNESS_WEIGHT = 0.6

# How hard we push pain toward whoever has suffered least so far.
ROTATION_WEIGHT = 20.0

SLOT_MINUTES = 30
SUBSAMPLE_MINUTES = 15


@dataclass
class Member:
    name: str
    tz: str
    work_start: float = 9.0
    work_end: float = 17.0
    sleep_start: float = 23.0
    sleep_end: float = 7.0
    # Accumulated pain from meetings already scheduled. This is what makes the
    # rotation work -- someone who took the last three bad calls gets protected.
    burden: float = 0.0

    def zone(self) -> ZoneInfo:
        return ZoneInfo(self.tz)


def _in_window(hour: float, start: float, end: float) -> bool:
    """Is `hour` inside [start, end)? The window may wrap past midnight."""
    hour %= 24
    if start <= end:
        return start <= hour < end
    return hour >= start or hour < end


def _circular_gap(a: float, b: float) -> float:
    d = abs(a - b) % 24
    return min(d, 24 - d)


def _hours_outside(hour: float, start: float, end: float) -> float:
    """How far `hour` sits from the nearest edge of the working window."""
    return min(_circular_gap(hour, start), _circular_gap(hour, end))


def hour_pain(hour: float, member: Member) -> float:
    """Pain of asking `member` to be present at their local `hour`."""
    hour %= 24
    if _in_window(hour, member.work_start, member.work_end):
        return 0.0
    if _in_window(hour, member.sleep_start, member.sleep_end):
        return SLEEP_PAIN
    # Awake, but off the clock. Pain grows faster than linearly: the fourth hour
    # past your workday costs more than the first.
    gap = _hours_outside(hour, member.work_start, member.work_end)
    return min(MAX_AWAKE_PAIN, 12.0 * gap ** 1.35)


def meeting_pain(start_utc: datetime, duration_min: int, member: Member) -> float:
    """Average pain across the meeting, sampled every 15 minutes.

    Sampling matters: a call that starts at 16:45 and runs an hour is mostly
    fine, and a single reading at the start hour would miss that it spills out.
    """
    samples = []
    elapsed = 0
    while elapsed < duration_min:
        local = start_utc.astimezone(member.zone()) + timedelta(minutes=elapsed)
        samples.append(hour_pain(local.hour + local.minute / 60.0, member))
        elapsed += SUBSAMPLE_MINUTES
    return sum(samples) / len(samples) if samples else 0.0


@dataclass
class MemberSlot:
    name: str
    tz: str
    local_label: str
    local_day_offset: int
    pain: float
    asleep: bool


@dataclass
class Slot:
    start_utc: datetime
    duration_min: int
    members: list[MemberSlot]
    mean_pain: float
    worst_pain: float
    score: float          # quality of the slot, ignoring history
    fair_score: float     # what we actually rank on, history included
    everyone_awake: bool

    @property
    def utc_label(self) -> str:
        return self.start_utc.strftime("%H:%M")


def _day_offset(local: datetime, reference: date) -> int:
    return (local.date() - reference).days


def score_slot(start_utc: datetime, duration_min: int, members: list[Member],
               reference_day: date) -> Slot:
    pains = [meeting_pain(start_utc, duration_min, m) for m in members]
    mean = sum(pains) / len(pains)
    worst = max(pains)

    # Punish lopsided slots. A 50/50 split beats one person at 0 and one at 100,
    # even though both average out the same.
    score = mean + UNFAIRNESS_WEIGHT * (worst - mean)

    rows = []
    for m, p in zip(members, pains):
        local = start_utc.astimezone(m.zone())
        rows.append(MemberSlot(
            name=m.name,
            tz=m.tz,
            local_label=local.strftime("%H:%M"),
            local_day_offset=_day_offset(local, reference_day),
            pain=round(p, 1),
            asleep=p >= SLEEP_PAIN,
        ))

    return Slot(
        start_utc=start_utc,
        duration_min=duration_min,
        members=rows,
        mean_pain=round(mean, 1),
        worst_pain=round(worst, 1),
        score=round(score, 1),
        fair_score=round(score, 1),
        everyone_awake=worst < SLEEP_PAIN,
    )


def _rotation_penalty(pains: list[float], members: list[Member]) -> float:
    """Nudge the painful slot toward whoever has carried the least of it so far.

    Without this the tool is just an overlap finder: it returns the same
    mathematically-optimal slot every week, and the same person eats it every
    week.

    Two details matter. We measure each person's burden against the team
    *average*, so under-burdened people actively attract the bad slot rather
    than merely not repelling it. And we weight by pain **squared**, because
    what we're really rotating is who takes the big hit -- without that, a
    scatter of minor inconveniences cancels out the signal entirely.
    """
    burdens = [m.burden for m in members]
    spread = max(burdens) - min(burdens)
    if spread <= 0:
        return 0.0  # nobody has history yet, nothing to correct for

    average = sum(burdens) / len(burdens)
    # Positive for the over-burdened, negative for those owed a turn.
    relative = [(b - average) / spread for b in burdens]
    return sum((p / 100.0) ** 2 * r for p, r in zip(pains, relative))


def plan(members: list[Member], day: date, duration_min: int = 60,
         earliest_utc: int = 0, latest_utc: int = 24) -> list[Slot]:
    """Score every candidate slot on `day` and return them, fairest first."""
    if not members:
        return []

    slots = []
    cursor = datetime.combine(day, time(0, 0), tzinfo=ZoneInfo("UTC"))
    end = cursor + timedelta(days=1)
    while cursor < end:
        if earliest_utc <= cursor.hour < latest_utc:
            slot = score_slot(cursor, duration_min, members, day)
            pains = [r.pain for r in slot.members]
            penalty = _rotation_penalty(pains, members) * ROTATION_WEIGHT
            slot.fair_score = round(slot.score + penalty, 1)
            slots.append(slot)
        cursor += timedelta(minutes=SLOT_MINUTES)

    slots.sort(key=lambda s: (not s.everyone_awake, s.fair_score, s.worst_pain))
    return slots


def heatstrip(members: list[Member], day: date) -> list[dict]:
    """Per-member pain for each hour of the UTC day, for the visual grid."""
    rows = []
    for m in members:
        cells = []
        for h in range(24):
            start = datetime.combine(day, time(h, 0), tzinfo=ZoneInfo("UTC"))
            local = start.astimezone(m.zone())
            p = hour_pain(local.hour + local.minute / 60.0, m)
            cells.append({
                "utc_hour": h,
                "local_label": local.strftime("%H:%M"),
                "pain": round(p, 1),
                "band": "sleep" if p >= SLEEP_PAIN else
                        "work" if p == 0 else
                        "edge" if p < 50 else "rough",
            })
        offset = m.zone().utcoffset(datetime.combine(day, time(12, 0)))
        hours = offset.total_seconds() / 3600 if offset else 0
        rows.append({
            "name": m.name,
            "tz": m.tz,
            "utc_offset": f"UTC{hours:+g}",
            "burden": round(m.burden, 1),
            "cells": cells,
        })
    return rows
