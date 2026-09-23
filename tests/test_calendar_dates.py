"""Tests build_calendar_dates() against real dates from the `holidays`
package's Colombia calendar -- including Ley Emiliani's Monday-shifting,
since that's exactly the kind of thing worth pinning down with a real date
rather than a synthetic one.
"""
from __future__ import annotations

import datetime as dt

from gtfs_pipeline.transform.calendar import SATURDAY, SUNDAY, WEEKDAY
from gtfs_pipeline.transform.calendar_dates import ADDED, REMOVED, build_calendar_dates


def _parse_gtfs_date(s: str) -> dt.date:
    return dt.date(int(s[:4]), int(s[4:6]), int(s[6:8]))


def test_weekday_holiday_swaps_to_sunday_pattern():
    # 2026-01-01 (Año Nuevo) is a Thursday
    df = build_calendar_dates(dt.date(2026, 1, 1), dt.date(2026, 1, 1))
    rows = {(r.service_id, r.date, r.exception_type) for r in df.itertuples()}
    assert rows == {
        (WEEKDAY, "20260101", REMOVED),
        (SUNDAY, "20260101", ADDED),
    }


def test_saturday_holiday_swaps_saturday_service_not_weekday():
    """Checks the invariant for every Saturday-falling holiday in a year
    (rather than needing to hand-pick one and hope it doesn't move): each
    must remove `saturday` service and add `sunday` service on that same
    date, never touching `weekday`.
    """
    df = build_calendar_dates(dt.date(2027, 1, 1), dt.date(2027, 12, 31))
    saturday_removed = df[(df["exception_type"] == REMOVED) & (df["service_id"] == SATURDAY)]
    assert not saturday_removed.empty  # sanity check the year picked actually has one
    for _, row in saturday_removed.iterrows():
        d = _parse_gtfs_date(row["date"])
        assert d.weekday() == 5
        matching_add = df[
            (df["service_id"] == SUNDAY) & (df["date"] == row["date"]) & (df["exception_type"] == ADDED)
        ]
        assert len(matching_add) == 1


def test_holiday_that_falls_on_sunday_produces_no_exception():
    # 2024-12-08 (La Inmaculada Concepción) genuinely falls on a Sunday --
    # `sunday` service already runs that day via calendar.txt, so no
    # calendar_dates.txt row should be generated for it at all.
    df = build_calendar_dates(dt.date(2024, 12, 8), dt.date(2024, 12, 8))
    assert df.empty


def test_dates_outside_range_are_excluded():
    df = build_calendar_dates(dt.date(2026, 6, 1), dt.date(2026, 6, 2))
    assert df.empty


def test_every_holiday_produces_exactly_a_remove_and_add_pair():
    df = build_calendar_dates(dt.date(2026, 1, 1), dt.date(2026, 12, 31))
    assert len(df) % 2 == 0
    for date, group in df.groupby("date"):
        types = sorted(group["exception_type"])
        assert types == [ADDED, REMOVED]
