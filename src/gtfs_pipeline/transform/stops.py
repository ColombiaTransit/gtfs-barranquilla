"""Builds GTFS stops.txt from the `stops` list embedded in each route's
scraped record (itself parsed from that route's KML -- see
sources/transmetro.py). COD_PARADA is a stop code shared across every
route that serves that physical stop, so this dedupes on that code rather
than emitting one row per route that happens to pass through it.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from ._routes_io import iter_routes, logger
from .text_cleaning import clean_text_field


def build_stops(route_jsonl_paths: list[Path]) -> pd.DataFrame:
    seen: dict[str, dict] = {}
    conflicts: list[str] = []
    empty_names: list[str] = []

    for route in iter_routes(route_jsonl_paths):
        for stop in route.get("stops", []):
            code = stop.get("cod_parada")
            if not code or (stop.get("estado") or "").upper() != "ACTIVO":
                continue

            name = clean_text_field(stop.get("nombre"))
            if not name:
                # a real MobilityData gtfs-validator run flagged 17 of
                # these as `missing_stop_name` errors -- an empty name is
                # worse than dropping the stop, since GTFS requires it
                empty_names.append(code)
                continue

            if code in seen and seen[code]["nombre"] != name:
                conflicts.append(
                    f"stop {code}: {seen[code]['nombre']!r} vs {name!r} "
                    f"(seen again on route {route.get('route_code')})"
                )
            seen.setdefault(code, {**stop, "nombre": name})

    if empty_names:
        logger.warning(
            "%d stop(s) had an empty/whitespace-only name after cleaning and "
            "were dropped rather than written with a blank stop_name -- codes: %s",
            len(empty_names), sorted(set(empty_names)),
        )

    if conflicts:
        logger.warning(
            "%d stop-name conflict(s) across routes -- kept whichever name "
            "was seen first, worth a human review:\n- %s",
            len(conflicts), "\n- ".join(conflicts),
        )

    if not seen:
        raise ValueError(
            "No active stops found in any route file. Either `gtfsbaq fetch` "
            "hasn't run yet, or every route's KML fetch failed -- check the "
            "warnings from the fetch stage."
        )

    rows = [
        {
            "stop_id": f"stop_{code}",
            "stop_code": code,
            "stop_name": s["nombre"],
            "stop_lat": s["lat"],
            "stop_lon": s["lon"],
            "location_type": 0,
        }
        for code, s in seen.items()
    ]
    return pd.DataFrame(rows).sort_values("stop_id").reset_index(drop=True)
