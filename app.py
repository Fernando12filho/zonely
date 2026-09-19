"""Zonely -- find a meeting time that doesn't always punish the same person."""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from flask import Flask, jsonify, render_template, request, Response

from zonely import state, zones
from zonely.scoring import Member, plan, heatstrip, SLOT_MINUTES

app = Flask(__name__)

DEFAULT_DURATION = 60
DURATIONS = [15, 30, 45, 60, 90, 120]
MAX_SLOTS = 8


def _parse_day(raw: str | None) -> date:
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return datetime.now(ZoneInfo("UTC")).date()


def _parse_duration(raw) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_DURATION
    return value if value in DURATIONS else DEFAULT_DURATION


def _slot_json(slot) -> dict:
    return {
        "start_utc": slot.start_utc.isoformat(),
        "utc_label": slot.utc_label,
        "duration_min": slot.duration_min,
        "mean_pain": slot.mean_pain,
        "worst_pain": slot.worst_pain,
        "score": slot.score,
        "fair_score": slot.fair_score,
        "everyone_awake": slot.everyone_awake,
        "members": [
            {
                "name": r.name,
                "tz": r.tz,
                "local_label": r.local_label,
                "day_offset": r.local_day_offset,
                "pain": r.pain,
                "asleep": r.asleep,
            }
            for r in slot.members
        ],
    }


def _default_team() -> list[Member]:
    return [
        Member(name="Ana", tz="America/Los_Angeles"),
        Member(name="Jo", tz="Europe/Berlin"),
        Member(name="Wei", tz="Asia/Singapore"),
    ]


@app.route("/")
def index():
    members = state.decode(request.args.get("t", "")) or _default_team()
    day = _parse_day(request.args.get("d"))
    duration = _parse_duration(request.args.get("m"))
    return render_template(
        "index.html",
        members=members,
        day=day.isoformat(),
        duration=duration,
        durations=DURATIONS,
        popular=zones.POPULAR,
        all_zones=zones.all_zones(),
        token=state.encode(members),
    )


@app.post("/api/plan")
def api_plan():
    payload = request.get_json(silent=True) or {}
    members = state.from_payload(payload.get("members", []))
    day = _parse_day(payload.get("day"))
    duration = _parse_duration(payload.get("duration"))

    if not members:
        return jsonify({"slots": [], "heatstrip": [], "token": "", "error": "Add at least one teammate."})

    slots = plan(members, day, duration_min=duration)
    return jsonify({
        "slots": [_slot_json(s) for s in slots[:MAX_SLOTS]],
        "heatstrip": heatstrip(members, day),
        "token": state.encode(members),
        "day": day.isoformat(),
        "duration": duration,
        "slot_minutes": SLOT_MINUTES,
    })


@app.get("/ics")
def ics():
    """Download the chosen slot as a calendar invite."""
    try:
        start = datetime.fromisoformat(request.args.get("start", ""))
    except ValueError:
        return Response("Bad start time", status=400)
    if start.tzinfo is None:
        start = start.replace(tzinfo=ZoneInfo("UTC"))
    start = start.astimezone(ZoneInfo("UTC"))
    duration = _parse_duration(request.args.get("m"))
    end = start + timedelta(minutes=duration)
    stamp = "%Y%m%dT%H%M%SZ"

    body = "\r\n".join([
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Zonely//EN",
        "BEGIN:VEVENT",
        f"UID:{start.strftime('%Y%m%dT%H%M%S')}@zonely",
        f"DTSTAMP:{datetime.now(ZoneInfo('UTC')).strftime(stamp)}",
        f"DTSTART:{start.strftime(stamp)}",
        f"DTEND:{end.strftime(stamp)}",
        "SUMMARY:Team sync (scheduled with Zonely)",
        "END:VEVENT",
        "END:VCALENDAR",
    ])
    return Response(body, mimetype="text/calendar",
                    headers={"Content-Disposition": "attachment; filename=zonely.ics"})


@app.get("/healthz")
def healthz():
    return {"ok": True}


if __name__ == "__main__":
    app.run(debug=True, port=int(os.environ.get("PORT", 5000)))
