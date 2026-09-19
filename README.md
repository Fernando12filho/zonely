# 🌍 Zonely

**Stop making the same person take the 11pm call.**

Most timezone tools find the overlap. That's the easy half. The hard half is that
when a team spans San Francisco, Berlin and Singapore there often *is* no
painless slot — so the tool returns the same mathematically-optimal time every
week, and the same person eats it every week.

Zonely scores every slot by how much it hurts, and then rotates the hurt.

## How it works

**Pain score.** Every half-hour slot gets a 0–100 score per teammate: 0 inside
their working day, 100 if it would wake them. Hours outside the workday cost
more the further out they go — the fourth hour past dinner hurts more than the
first.

**Fairness.** A slot's score is the team's average pain *plus a penalty for
being lopsided*. Optimising the average alone will happily sacrifice one person
forever to keep everyone else comfortable.

**Rotation.** Log a meeting and whoever took the hit carries a *burden*. Next
time you plan, Zonely pushes pain toward whoever has carried the least. Over
eight weekly meetings with an SF/Berlin/Singapore team, the bad slot lands 4–4
instead of 8–0.

## Running locally

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python app.py              # http://localhost:5000
pytest -q                  # 17 tests
```

## Design notes

- **No database.** The team is encoded into the URL, so every plan is a link you
  can paste into Slack. A typical eight-person team is ~360 characters.
- **No API keys.** All timezone maths uses Python's stdlib `zoneinfo`, which
  ships the IANA database — 598 zones, daylight saving included. Tests cover the
  usual traps: the US and EU shifting on different dates, southern-hemisphere
  DST running backwards, and India's half-hour offset.
- **No build step.** Vanilla JS and one stylesheet.

## Layout

```
app.py              Flask routes: /, /api/plan, /ics, /healthz
zonely/scoring.py   the pain model, slot ranking and rotation
zonely/state.py     URL encode/decode for the shareable team
zonely/zones.py     timezone catalogue from the stdlib
templates/          Jinja
static/             CSS + JS
tests/              pytest
```

## Deploying

Configured for [Railway](https://railway.app) via `railway.toml` — health check
on `/healthz`, gunicorn with two workers. `Procfile` is included so it also runs
unchanged on any Heroku-style host.
