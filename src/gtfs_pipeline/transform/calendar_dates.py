"""Builds GTFS calendar_dates.txt: on Colombian public holidays, every
route's own scraped schedule already treats the day as "Domingo y
festivos" (see the horario text parsed in horario.py, which maps that
phrase to the same `sunday` service_id as an actual Sunday) -- so a
holiday that falls on a weekday or Saturday needs a calendar_dates.txt
exception to REMOVE that day's normal service and ADD the `sunday`
service instead, otherwise a rider on a Tuesday holiday would see both
the weekday trips AND (incorrectly) no festivo-hours trips at all, since
calendar.txt alone can't express "this specific Tuesday behaves like a
Sunday".

Holiday dates come from the `holidays` package's Colombia calendar, which
already accounts for Colombia's "Ley Emiliani" (many holidays are observed
on the following Monday rather than their traditional date) -- so these
are the dates transit actually runs festivo hours on, not the raw
traditional dates.
"""
from __future__ import annotations

import datetime as dt

import holidays
import pandas as pd

from .calendar import SATURDAY, SUNDAY, WEEKDAY

ADDED, REMOVED = 1, 2  # GTFS calendar_dates.txt exception_type values


def build_calendar_dates(start_date: dt.date | None = None, end_date: dt.date | None = None) -> pd.DataFrame:
    start_date = start_date or dt.datetime.now(tz=dt.UTC).date()
    end_date = end_date or (start_date + dt.timedelta(days=365))

    years = sorted({start_date.year, end_date.year})
    co_holidays = holidays.Colombia(years=years)

    rows = []
    for holiday_date in sorted(co_holidays):
        if not (start_date <= holiday_date <= end_date):
            continue
        if holiday_date.weekday() == 6:  # already a Sunday -- `sunday` service already runs, no exception needed
            continue

        normal_service = WEEKDAY if holiday_date.weekday() < 5 else SATURDAY
        date_str = holiday_date.strftime("%Y%m%d")
        rows.append({"service_id": normal_service, "date": date_str, "exception_type": REMOVED})
        rows.append({"service_id": SUNDAY, "date": date_str, "exception_type": ADDED})

    return pd.DataFrame(rows, columns=["service_id", "date", "exception_type"])
