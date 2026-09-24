"""Estimates stop-to-stop timing within a trip from real stop coordinates,
replacing a flat per-stop placeholder that ignored actual distance
entirely (every consecutive pair got the same 60 seconds, whether they
were 50m or 2km apart -- not realistic, and worth fixing now that the
rest of the feed has real headways/windows).

Still NOT real travel-time data -- no AVL/timetable source for that
exists -- but distance-aware and far closer to reality than a flat
constant. Two assumptions carry the estimate, both named here so they're
easy to revisit if better data ever turns up:
  - CIRCUITY_FACTOR: straight-line (great-circle) distance between two
    stops underestimates actual road distance, since roads bend and
    stops aren't on a straight line between each other. A factor of 1.3
    is a common rule-of-thumb multiplier for urban street grids -- not
    measured for Barranquilla specifically.
  - MOVING_SPEED_KMH: an assumed average speed while the vehicle is
    actually moving between stops (dwell time at each stop is added
    separately, below). Troncal routes run in dedicated bus lanes (BRT)
    and are assumed faster than alimentadora routes in mixed traffic --
    a reasonable distinction to draw, but still an assumption, not a
    measurement.
"""
from __future__ import annotations

import math
from itertools import pairwise

EARTH_RADIUS_M = 6_371_000

CIRCUITY_FACTOR = 1.3
MOVING_SPEED_KMH = {"troncal": 22.0, "alimentadora": 16.0}
DEFAULT_MOVING_SPEED_KMH = MOVING_SPEED_KMH["alimentadora"]
DWELL_SECONDS = 20  # doors open for boarding/alighting at each stop
MIN_TRAVEL_SECONDS = 30  # floor, so two very closely-spaced stops don't get ~0s


def haversine_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two lat/lon points, in meters."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def stop_time_offsets_seconds(stops: list[dict], system: str) -> list[int]:
    """Cumulative seconds from the first stop's departure, for each stop
    in `stops` (each needing "lat"/"lon" keys, in travel order) -- the
    first stop's own offset is always 0. Every stop after the first adds
    DWELL_SECONDS (time at the previous stop) plus an estimated travel
    time from the previous stop, floored at MIN_TRAVEL_SECONDS.
    """
    speed_m_s = MOVING_SPEED_KMH.get(system, DEFAULT_MOVING_SPEED_KMH) * 1000 / 3600

    offsets = [0]
    for prev, curr in pairwise(stops):
        distance_m = haversine_distance_m(prev["lat"], prev["lon"], curr["lat"], curr["lon"]) * CIRCUITY_FACTOR
        travel_s = max(MIN_TRAVEL_SECONDS, round(distance_m / speed_m_s))
        offsets.append(offsets[-1] + DWELL_SECONDS + travel_s)
    return offsets
