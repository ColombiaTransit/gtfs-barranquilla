"""Loads config/alimentadora_frequencies.yml and config/troncal_frequencies.yml
and matches each against a scraped route's own declared `route_code` text,
for whichever service day (weekday/saturday/sunday) is being built.

Two separate normalizers/tables, not one, because the two systems' route
codes have genuinely different shapes: alimentadora codes are compound
("A1-2", "U-30" -- letter, optional hyphen, one or two hyphen-joined
numbers) while troncal codes are a plain letter-plus-number with no hyphen
at all ("B1", "S10", "R40"). Matching isn't a plain dict lookup for either:
the site is inconsistent about code formatting (hyphen-or-not), and at
least one alimentadora route's displayed code doesn't even match what its
own URL slug implies (see normalize_alimentadora_code's docstring). Each
normalizer reassembles a route's text into that table's own key format.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml

from ..config import REPO_ROOT
from .calendar import SATURDAY, SUNDAY, WEEKDAY

ALIMENTADORA_PATH = REPO_ROOT / "config" / "alimentadora_frequencies.yml"
TRONCAL_PATH = REPO_ROOT / "config" / "troncal_frequencies.yml"

_ALIMENTADORA_CODE_RE = re.compile(r"^\s*([AU])-?(\d+)(?:-(\d+))?", re.IGNORECASE)
_TRONCAL_CODE_RE = re.compile(r"^\s*([A-Za-z]+)(\d+)", re.IGNORECASE)
_VALID_SERVICE_IDS = {WEEKDAY, SATURDAY, SUNDAY}


def normalize_alimentadora_code(text: str | None) -> str | None:
    """"A9-4 Carrera 46..." -> "A9-4"; "U-30 Universidades" -> "U30";
    "B1" -> None (doesn't match the [AU] alimentadora-code pattern -- that's
    correct, troncal codes live in the other table).
    """
    if not text:
        return None
    m = _ALIMENTADORA_CODE_RE.match(text)
    if not m:
        return None
    letter, num1, num2 = m.group(1).upper(), m.group(2), m.group(3)
    return f"{letter}{num1}" + (f"-{num2}" if num2 else "")


def normalize_troncal_code(text: str | None) -> str | None:
    """"B1" -> "B1"; "S10" -> "S10"; "A1-2 Carrera Ocho" -> None (an
    alimentadora code -- correct, it lives in the other table: the letter
    run must be followed directly by digits, with nothing else in between,
    which "A1-2" satisfies for "A1" alone but that's a different route
    code space entirely and isn't in this table regardless).
    """
    if not text:
        return None
    m = _TRONCAL_CODE_RE.match(text)
    if not m:
        return None
    return f"{m.group(1).upper()}{m.group(2)}"


@lru_cache(maxsize=2)
def _load_all_days(path: Path) -> dict[str, dict[str, list[dict]]]:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return {day: (data.get(day) or {}).get("routes", {}) for day in _VALID_SERVICE_IDS}


def get_alimentadora_bands(
    route_code_text: str | None, service_id: str, path: Path = ALIMENTADORA_PATH
) -> list[dict] | None:
    """Real frequency bands for an alimentadora route on the given service
    day, or None (no match, wrong table for a troncal code, or an unknown
    service_id).
    """
    if service_id not in _VALID_SERVICE_IDS:
        return None
    key = normalize_alimentadora_code(route_code_text)
    if key is None:
        return None
    return _load_all_days(path)[service_id].get(key)


def get_troncal_bands(
    route_code_text: str | None, service_id: str, path: Path = TRONCAL_PATH
) -> list[dict] | None:
    """Real frequency bands for a troncal route on the given service day,
    or None (no match, wrong table for an alimentadora code, or an unknown
    service_id).
    """
    if service_id not in _VALID_SERVICE_IDS:
        return None
    key = normalize_troncal_code(route_code_text)
    if key is None:
        return None
    return _load_all_days(path)[service_id].get(key)


def get_bands(route: dict, service_id: str) -> list[dict] | None:
    """Dispatches to the right table based on the scraped route's own
    `system` field ("alimentadora" or "troncal") -- this is what
    trips_and_stop_times.py actually calls; the two get_*_bands() above are
    exposed separately mainly because they're easier to test in isolation.
    """
    if route.get("system") == "alimentadora":
        return get_alimentadora_bands(route.get("route_code"), service_id)
    if route.get("system") == "troncal":
        return get_troncal_bands(route.get("route_code"), service_id)
    return None
