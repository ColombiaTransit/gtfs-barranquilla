"""Builds GTFS shapes.txt directly from each route's `shape_coordinates`
(scraped from its KML LineString -- see sources/transmetro.py).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from ._routes_io import iter_routes, route_id


def build_shapes(route_jsonl_paths: list[Path], *, include_suspended: bool = False) -> pd.DataFrame:
    rows = []
    for route in iter_routes(route_jsonl_paths, include_suspended=include_suspended):
        coords = route.get("shape_coordinates") or []
        if not coords:
            continue
        shape_id = f"shape_{route_id(route)}"
        for seq, (lon, lat) in enumerate(coords):
            rows.append(
                {"shape_id": shape_id, "shape_pt_lat": lat, "shape_pt_lon": lon, "shape_pt_sequence": seq}
            )
    return pd.DataFrame(rows)


def shape_id_for(route: dict) -> str:
    return f"shape_{route_id(route)}"
