"""Builds GTFS routes.txt from the scraped route records.

route_long_name is assembled from the first/last active stop (by scraped
sequence) rather than the "Recorrido" paragraph -- that paragraph is a
prose description (goes in route_desc), not a short "origin - destination"
label, which is what route_long_name is meant to be per the GTFS spec.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from ._routes_io import iter_routes, route_id, sorted_active_stops

ROUTE_TYPE_BUS = 3


def build_routes(route_jsonl_paths: list[Path], *, include_suspended: bool = False) -> pd.DataFrame:
    rows = []
    for route in iter_routes(route_jsonl_paths, include_suspended=include_suspended):
        stops = sorted_active_stops(route)
        long_name = f"{stops[0]['nombre']} - {stops[-1]['nombre']}" if stops else ""

        rows.append(
            {
                "route_id": route_id(route),
                "route_short_name": route["route_code"],
                "route_long_name": long_name,
                "route_desc": route.get("recorrido_text") or "",
                "route_type": ROUTE_TYPE_BUS,
            }
        )

    if not rows:
        raise ValueError(
            "No routes found -- either `gtfsbaq fetch` hasn't run, or every "
            "route was suspended/failed to scrape."
        )
    return pd.DataFrame(rows).drop_duplicates(subset="route_id").reset_index(drop=True)
