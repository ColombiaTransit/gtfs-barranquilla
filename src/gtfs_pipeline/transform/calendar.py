"""Builds GTFS calendar.txt.

Three generic service_ids (weekday / saturday / sunday) cover every route:
calendar.txt only controls which *days* a service runs, and every scraped
route's schedule already distinguishes "Lunes a viernes" / "Sábados" /
"Domingo y festivos" at the trip level (see trips_and_stop_times.py, which
parses each route's actual operating-hours text and assigns trips to these
service_ids) -- so no route-specific calendar rows are needed.

start_date/end_date are just today's date is picked and a wide validity
window is set (1 year) since Transmetro's pages give operating hours, not
an explicit calendar validity range -- there is no upstream source for
that. Widen/narrow as needed once real service-change dates are known.
"""
from __future__ import annotations

import datetime as dt

import pandas as pd

WEEKDAY, SATURDAY, SUNDAY = "weekday", "saturday", "sunday"


def build_calendar(start_date: dt.date | None = None, end_date: dt.date | None = None) -> pd.DataFrame:
    start_date = start_date or dt.datetime.now(tz=dt.UTC).date()
    end_date = end_date or (start_date + dt.timedelta(days=365))
    start, end = start_date.strftime("%Y%m%d"), end_date.strftime("%Y%m%d")

    return pd.DataFrame(
        [
            {"service_id": WEEKDAY, "monday": 1, "tuesday": 1, "wednesday": 1, "thursday": 1,
             "friday": 1, "saturday": 0, "sunday": 0, "start_date": start, "end_date": end},
            {"service_id": SATURDAY, "monday": 0, "tuesday": 0, "wednesday": 0, "thursday": 0,
             "friday": 0, "saturday": 1, "sunday": 0, "start_date": start, "end_date": end},
            {"service_id": SUNDAY, "monday": 0, "tuesday": 0, "wednesday": 0, "thursday": 0,
             "friday": 0, "saturday": 0, "sunday": 1, "start_date": start, "end_date": end},
        ]
    )
