"""Tests both normalizers and both get_*_bands() lookups against the real
formatting inconsistencies seen in scraped route codes, plus the top-level
get_bands() dispatcher that trips_and_stop_times.py actually calls.
"""
from __future__ import annotations

from gtfs_pipeline.transform.calendar import SATURDAY, SUNDAY, WEEKDAY
from gtfs_pipeline.transform.frequency_reference import (
    get_alimentadora_bands,
    get_bands,
    get_troncal_bands,
    normalize_alimentadora_code,
    normalize_troncal_code,
)

# --- alimentadora normalizer ---


def test_normalize_alimentadora_handles_hyphen_after_letter():
    assert normalize_alimentadora_code("U-30 Universidades (opera con desvío)") == "U30"


def test_normalize_alimentadora_handles_compound_code_unchanged():
    assert normalize_alimentadora_code("A1-2 Carrera Ocho") == "A1-2"


def test_normalize_alimentadora_handles_mismatched_slug_using_the_displayed_code():
    # the real case that broke a naive lookup: this route's URL slug says
    # "u30", but its own displayed title says A9-4 -- normalize must use
    # the displayed text, not anything slug-derived
    assert normalize_alimentadora_code("A9-4 Carrera 46 / fines de semana") == "A9-4"


def test_normalize_alimentadora_returns_none_for_troncal_codes():
    assert normalize_alimentadora_code("B1") is None
    assert normalize_alimentadora_code("R10") is None


def test_normalize_alimentadora_returns_none_for_empty_input():
    assert normalize_alimentadora_code(None) is None
    assert normalize_alimentadora_code("") is None


# --- troncal normalizer ---


def test_normalize_troncal_simple_codes():
    assert normalize_troncal_code("B1") == "B1"
    assert normalize_troncal_code("S10") == "S10"
    assert normalize_troncal_code("R40") == "R40"


def test_normalize_troncal_returns_none_for_empty_input():
    assert normalize_troncal_code(None) is None
    assert normalize_troncal_code("") is None


# --- alimentadora bands ---


def test_get_alimentadora_bands_single_band_route_all_three_days():
    assert get_alimentadora_bands("A1-2 Carrera Ocho", WEEKDAY) == [
        {"start": "05:10", "end": "22:13", "headway_minutes": 12}
    ]
    assert get_alimentadora_bands("A1-2", SATURDAY) == [{"start": "05:15", "end": "22:14", "headway_minutes": 12}]
    assert get_alimentadora_bands("A1-2", SUNDAY) == [{"start": "06:00", "end": "21:16", "headway_minutes": 12}]


def test_get_alimentadora_bands_merged_band_weekday():
    # A5-4's weekday source PDF row visually merges the mañana+valle
    # columns into one wider band -- pinned as a real test.
    bands = get_alimentadora_bands("A5-4", WEEKDAY)
    assert bands == [
        {"start": "05:00", "end": "15:30", "headway_minutes": 12},
        {"start": "15:30", "end": "22:30", "headway_minutes": 9},
    ]


def test_get_alimentadora_bands_u30_saturday_merged_cell_confirmed_visually():
    # U30's Saturday row had 2 frequency numbers but 3 time windows in the
    # extracted text -- resolved by rendering the actual PDF page: 12
    # minutes is one merged cell spanning the last two windows.
    bands = get_alimentadora_bands("U-30 Universidades", SATURDAY)
    assert bands == [
        {"start": "05:00", "end": "09:30", "headway_minutes": 8},
        {"start": "09:30", "end": "22:00", "headway_minutes": 12},
    ]


def test_get_alimentadora_bands_returns_none_for_unmatched_route_or_day():
    assert get_alimentadora_bands("B1", WEEKDAY) is None  # troncal code
    assert get_alimentadora_bands("A99-9 Not A Real Route", WEEKDAY) is None
    assert get_alimentadora_bands("A1-2", "not_a_real_service_id") is None
    # A9-4 doesn't appear in any of the three 2024 alimentadora tables at all
    assert get_alimentadora_bands("A9-4 Carrera 46 / fines de semana", WEEKDAY) is None


# --- troncal bands ---


def test_get_troncal_bands_three_band_route():
    bands = get_troncal_bands("B1", WEEKDAY)
    assert bands == [
        {"start": "05:00", "end": "09:30", "headway_minutes": 4},
        {"start": "09:30", "end": "14:30", "headway_minutes": 7},
        {"start": "14:30", "end": "21:30", "headway_minutes": 4},
    ]


def test_get_troncal_bands_r10_has_a_real_midday_gap():
    # R10 genuinely stops running between the morning and afternoon peaks
    # on weekdays -- represented correctly as simply no band covering
    # 09:30-11:30, not as a data error.
    bands = get_troncal_bands("R10", WEEKDAY)
    assert bands == [
        {"start": "05:00", "end": "09:30", "headway_minutes": 3},
        {"start": "11:30", "end": "15:30", "headway_minutes": 8},
        {"start": "15:30", "end": "21:00", "headway_minutes": 3},
    ]


def test_get_troncal_bands_r10_has_no_sunday_service_at_all():
    assert get_troncal_bands("R10", SUNDAY) is None


def test_get_troncal_bands_s40_uses_the_2018_figure_on_weekdays_only():
    # S40 has no current source for a headway -- the one number available
    # anywhere comes from a 2018 news article, used at the user's explicit
    # instruction. It only covers weekdays; Saturday/Sunday still have no
    # data for S40 from any source and fall back to the placeholder.
    assert get_troncal_bands("S40", WEEKDAY) == [{"start": "16:00", "end": "19:00", "headway_minutes": 5}]
    assert get_troncal_bands("S40", SATURDAY) is None
    assert get_troncal_bands("S40", SUNDAY) is None


def test_get_troncal_bands_returns_none_for_alimentadora_codes():
    assert get_troncal_bands("A1-2 Carrera Ocho", WEEKDAY) is None


# --- top-level dispatcher ---


def test_get_bands_dispatches_by_system():
    troncal_route = {"system": "troncal", "route_code": "B1"}
    alimentadora_route = {"system": "alimentadora", "route_code": "A1-2 Carrera Ocho"}

    assert get_bands(troncal_route, WEEKDAY) == get_troncal_bands("B1", WEEKDAY)
    assert get_bands(alimentadora_route, WEEKDAY) == get_alimentadora_bands("A1-2 Carrera Ocho", WEEKDAY)


def test_get_bands_returns_none_for_unknown_system():
    assert get_bands({"system": "some_future_system", "route_code": "X1"}, WEEKDAY) is None
    assert get_bands({"route_code": "B1"}, WEEKDAY) is None  # no "system" key at all
