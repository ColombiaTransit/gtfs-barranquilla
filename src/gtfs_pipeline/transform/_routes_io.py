"""Shared helper for reading data/raw/{troncal,alimentadora}_routes.jsonl.

Every transform/*.py module that needs the scraped route records goes
through this, so "what counts as an active, usable route record" is
defined in exactly one place.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from pathlib import Path

logger = logging.getLogger(__name__)


def iter_routes(paths: list[Path], *, include_suspended: bool = False) -> Iterator[dict]:
    for path in paths:
        if not path.exists():
            logger.warning("route file not found, skipping: %s", path)
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                route = json.loads(line)
                if route.get("error"):
                    logger.warning(
                        "skipping %s (%s) -- scrape failed: %s",
                        route.get("slug"), route.get("system"), route["error"],
                    )
                    continue
                if route.get("suspended") and not include_suspended:
                    continue
                yield route


def route_id(route: dict) -> str:
    # the slug is unique and stable even for a route with no KML data yet
    # (e.g. a scrape failure); prefer it over anything KML-derived.
    return f"route_{route['system']}_{route['slug']}"


def sorted_active_stops(route: dict) -> list[dict]:
    """This route's stops, in travel order, excluding any the KML itself
    flagged as inactive (ESTADO != ACTIVO) or with no usable sequence."""
    stops = [
        s for s in route.get("stops", [])
        if s.get("cod_parada") and s.get("secuencia") is not None
        and (s.get("estado") or "").upper() == "ACTIVO"
    ]
    return sorted(stops, key=lambda s: s["secuencia"])
