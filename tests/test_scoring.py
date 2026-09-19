from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from zonely.scoring import Member, hour_pain, meeting_pain, plan, heatstrip


def m(name="A", tz="UTC", **kw):
    return Member(name=name, tz=tz, **kw)


class TestHourPain:
    def test_workday_is_painless(self):
        assert hour_pain(9, m()) == 0
        assert hour_pain(13, m()) == 0

    def test_sleep_is_maximum(self):
        assert hour_pain(3, m()) == 100
        assert hour_pain(23.5, m()) == 100

    def test_pain_grows_faster_than_linearly(self):
        first = hour_pain(18, m())
        second = hour_pain(19, m())
        third = hour_pain(20, m())
        assert 0 < first < second < third
        assert (third - second) > (second - first)

    def test_sleep_window_wraps_midnight(self):
        night = m(sleep_start=22, sleep_end=6)
        assert hour_pain(23, night) == 100
        assert hour_pain(2, night) == 100
        assert hour_pain(12, night) == 0

    def test_night_owl_shifts_the_whole_curve(self):
        owl = m(work_start=14, work_end=22, sleep_start=3, sleep_end=11)
        assert hour_pain(21, owl) == 0
        assert hour_pain(9, owl) == 100


class TestMeetingPain:
    def test_meeting_spilling_past_the_workday_costs_more(self):
        person = m(tz="UTC")
        inside = meeting_pain(datetime(2026, 10, 14, 14, tzinfo=ZoneInfo("UTC")), 60, person)
        spilling = meeting_pain(datetime(2026, 10, 14, 16, 45, tzinfo=ZoneInfo("UTC")), 60, person)
        assert inside == 0
        assert spilling > 0

    def test_longer_meetings_are_sampled_throughout(self):
        person = m(tz="UTC")
        short = meeting_pain(datetime(2026, 10, 14, 16, tzinfo=ZoneInfo("UTC")), 30, person)
        long = meeting_pain(datetime(2026, 10, 14, 16, tzinfo=ZoneInfo("UTC")), 240, person)
        assert long > short


class TestPlan:
    def test_prefers_slots_where_everyone_is_awake(self):
        team = [m("Ana", "America/New_York"), m("Jo", "Europe/London")]
        best = plan(team, date(2026, 10, 14))[0]
        assert best.everyone_awake
        assert best.worst_pain == 0

    def test_impossible_spread_still_returns_the_least_bad(self):
        team = [m("Ana", "America/Los_Angeles"), m("Wei", "Asia/Singapore")]
        slots = plan(team, date(2026, 10, 14))
        assert slots, "must always offer something"
        assert slots[0].fair_score <= slots[-1].fair_score

    def test_lopsided_slots_lose_to_shared_pain(self):
        """One person at 100 should rank worse than two people at 50."""
        team = [m("Ana", "America/Los_Angeles"), m("Jo", "Europe/Berlin"),
                m("Wei", "Asia/Singapore")]
        for slot in plan(team, date(2026, 10, 14)):
            spread = slot.worst_pain - slot.mean_pain
            assert slot.score >= slot.mean_pain
            if spread > 0:
                assert slot.score > slot.mean_pain

    def test_history_rotates_the_recommendation(self):
        def best_victim(burdened):
            team = [
                m("Ana", "America/Los_Angeles", burden=255 if burdened == "Ana" else 0),
                m("Jo", "Europe/Berlin"),
                m("Wei", "Asia/Singapore", burden=255 if burdened == "Wei" else 0),
            ]
            top = plan(team, date(2026, 10, 14))[0]
            return max(top.members, key=lambda r: r.pain).name

        assert best_victim("Ana") == "Wei"
        assert best_victim("Wei") == "Ana"

    def test_empty_team_is_not_an_error(self):
        assert plan([], date(2026, 10, 14)) == []


class TestDaylightSaving:
    """The bug every timezone tool ships with. Offsets are not constant."""

    def test_us_and_eu_shift_on_different_dates(self):
        team = [m("Ana", "America/New_York"), m("Jo", "Europe/London")]
        # Late October 2026: the EU has fallen back, the US has not yet.
        gap_before = plan(team, date(2026, 10, 20))[0].start_utc.hour
        gap_after = plan(team, date(2026, 11, 3))[0].start_utc.hour
        assert gap_before != gap_after, "overlap must move when the clocks do"

    def test_southern_hemisphere_runs_the_other_way(self):
        person = m("Bea", "Australia/Sydney")
        jan = heatstrip([person], date(2026, 1, 15))[0]["utc_offset"]
        jul = heatstrip([person], date(2026, 7, 15))[0]["utc_offset"]
        assert jan == "UTC+11" and jul == "UTC+10"

    def test_half_hour_offsets_are_handled(self):
        row = heatstrip([m("Raj", "Asia/Kolkata")], date(2026, 10, 14))[0]
        assert row["utc_offset"] == "UTC+5.5"


class TestHeatstrip:
    def test_covers_the_full_day_for_every_member(self):
        rows = heatstrip([m("Ana", "America/Chicago"), m("Jo", "Africa/Lagos")],
                         date(2026, 10, 14))
        assert len(rows) == 2
        assert all(len(r["cells"]) == 24 for r in rows)

    def test_every_cell_is_classified(self):
        rows = heatstrip([m("Ana", "Asia/Tokyo")], date(2026, 10, 14))
        bands = {c["band"] for c in rows[0]["cells"]}
        assert bands <= {"work", "edge", "rough", "sleep"}
        assert "work" in bands and "sleep" in bands
