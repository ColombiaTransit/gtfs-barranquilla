"""Builds GTFS trips.txt, stop_times.txt, and frequencies.txt.

Operating *windows* come from each route's scraped "Horario de rutas" text
(via horario.py). *Headways* (how often a bus actually comes) are real for
every service day (weekday/Saturday/Sunday) on both troncal and
alimentadora routes matched in frequency_reference.py (from six scraped
PDFs total -- see config/alimentadora_frequencies.yml and
config/troncal_frequencies.yml for exact provenance and coverage per
system and day); everywhere else -- any route not present in a given day's
matching reference table -- still uses an obviously-fake `headway_secs`
placeholder for that day, since no source has been found.

stop_times.txt uses a fixed per-stop dwell placeholder throughout: no
inter-stop travel time source exists yet for any route.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from ._routes_io import iter_routes, route_id, sorted_active_stops
from .frequency_reference import get_bands
from .horario import parse_horario_lines
from .shapes import shape_id_for

PLACEHOLDER_HEADWAY_SECS = 9999  # obviously-fake; used wherever no real headway is known
DWELL_SECONDS_PER_STOP = 60  # obviously-approximate; no inter-stop timing source yet


def build_trips_stop_times_frequencies(
    route_jsonl_paths: list[Path], *, include_suspended: bool = False
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    trips_rows, stop_times_rows, frequencies_rows = [], [], []

    for route in iter_routes(route_jsonl_paths, include_suspended=include_suspended):
        stops = sorted_active_stops(route)
        windows = parse_horario_lines(route.get("horario_lines") or [])
        if not stops or not windows:
            continue  # nothing to build a trip from -- not an error, just incomplete data for this route

        r_id = route_id(route)
        has_shape = bool(route.get("shape_coordinates"))

        for service_id, start_time, end_time in windows:
            trip_id = f"{r_id}_{service_id}"
            trip = {"route_id": r_id, "service_id": service_id, "trip_id": trip_id, "direction_id": 0}
            if has_shape:
                trip["shape_id"] = shape_id_for(route)
            trips_rows.append(trip)

            base = _time_to_seconds(start_time)
            for seq, stop in enumerate(stops):
                t = _seconds_to_gtfs_time(base + seq * DWELL_SECONDS_PER_STOP)
                stop_times_rows.append(
                    {
                        "trip_id": trip_id,
                        "arrival_time": t,
                        "departure_time": t,
                        "stop_id": f"stop_{stop['cod_parada']}",
                        "stop_sequence": seq,
                    }
                )

            bands = get_bands(route, service_id)
            if bands:
                # real headways: one frequencies.txt row per time band, all
                # sharing this same trip_id as their "template" trip
                for band in bands:
                    frequencies_rows.append(
                        {
                            "trip_id": trip_id,
                            "start_time": band["start"] + ":00",
                            "end_time": band["end"] + ":00",
                            "headway_secs": band["headway_minutes"] * 60,
                        }
                    )
            else:
                frequencies_rows.append(
                    {
                        "trip_id": trip_id,
                        "start_time": start_time,
                        "end_time": end_time,
                        "headway_secs": PLACEHOLDER_HEADWAY_SECS,
                    }
                )

    return (
        pd.DataFrame(trips_rows),
        pd.DataFrame(stop_times_rows),
        pd.DataFrame(frequencies_rows),
    )


def _time_to_seconds(hms: str) -> int:
    h, m, s = (int(x) for x in hms.split(":"))
    return h * 3600 + m * 60 + s


def _seconds_to_gtfs_time(total_seconds: int) -> str:
    h, rem = divmod(total_seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"
