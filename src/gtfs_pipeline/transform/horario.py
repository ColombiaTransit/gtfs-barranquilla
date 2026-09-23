"""Parses the "Horario de rutas" text scraped from each route page (e.g.
"Lunes a viernes: de 5:00 a.m. a 6:22 p.m.") into (service_id, start_time,
end_time) triples GTFS can use.

Kept separate from trips_and_stop_times.py so the parsing logic -- the
part most likely to need a tweak as more routes are scraped and edge cases
in the site's phrasing turn up -- can be unit-tested against real strings
without touching the GTFS-assembly logic at all.
"""
from __future__ import annotations

import logging
import re

from .calendar import SATURDAY, SUNDAY, WEEKDAY

logger = logging.getLogger(__name__)

_DAY_TYPE_PATTERNS = [
    (WEEKDAY, re.compile(r"lunes\s+a\s+viernes", re.IGNORECASE)),
    (SATURDAY, re.compile(r"s[aá]bados?", re.IGNORECASE)),
    (SUNDAY, re.compile(r"domingo", re.IGNORECASE)),  # covers "Domingo y festivos"
]

# e.g. "5:00 a.m.", "6:22 p.m.", "5:00 am.", "7:22 pm." -- the site isn't
# consistent about the dots, so the pattern tolerates them being optional.
_TIME_RE = re.compile(r"(\d{1,2}):(\d{2})\s*([ap])\.?\s*m\.?", re.IGNORECASE)


def parse_horario_lines(lines: list[str]) -> list[tuple[str, str, str]]:
    """Returns [(service_id, start_time, end_time), ...], skipping any line
    that doesn't match a known day-type or doesn't contain two parseable
    times -- logged as a warning rather than raised, since one unparseable
    route shouldn't stop the whole transform stage.
    """
    windows = []
    for line in lines:
        service_id = _match_day_type(line)
        times = _TIME_RE.findall(line)

        if service_id is None or len(times) < 2:
            logger.warning("could not parse schedule line, skipping: %r", line)
            continue

        start = _to_24h(*times[0])
        end = _to_24h(*times[1])
        windows.append((service_id, start, end))

    return windows


def _match_day_type(line: str) -> str | None:
    for service_id, pattern in _DAY_TYPE_PATTERNS:
        if pattern.search(line):
            return service_id
    return None


def _to_24h(hour: str, minute: str, meridiem: str) -> str:
    h = int(hour) % 12
    if meridiem.lower() == "p":
        h += 12
    return f"{h:02d}:{minute}:00"
