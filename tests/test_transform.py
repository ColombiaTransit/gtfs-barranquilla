"""End-to-end test of the transform stage using one realistic route record
(B1's real KML-derived stops/shape, with schedule text matching what was
actually scraped from the B1 page) plus a suspended route, to check that
suspended routes are excluded by default and included with the flag.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from gtfs_pipeline.sources.transmetro import parse_kml
from gtfs_pipeline.transform.calendar import SATURDAY, SUNDAY, WEEKDAY
from gtfs_pipeline.transform.horario import parse_horario_lines
from gtfs_pipeline.transform.routes import build_routes
from gtfs_pipeline.transform.shapes import build_shapes
from gtfs_pipeline.transform.stops import build_stops
from gtfs_pipeline.transform.trips_and_stop_times import build_trips_stop_times_frequencies

FIXTURE = Path(__file__).parent / "fixtures" / "B1.kml"

B1_HORARIO_LINES = [
    "Lunes a viernes: de 5:00 a.m. a 6:22 p.m.",
    "Sábados: de 5:00 am. a 7:22 pm.",
    "Domingo y festivos: de 5:30 a.m. a 6:22 p.m.",
]


@pytest.fixture
def route_jsonl(tmp_path):
    kml_data = parse_kml(FIXTURE.read_text(encoding="utf-8"))
    b1 = {
        "system": "troncal", "slug": "b1", "label": "B1", "suspended": False,
        "route_code": "B1", "detail_url": "https://transmetro.gov.co/sistema/rutas_troncales/b1/",
        "recorrido_text": "Servicio corriente Portal de Soledad - Parque Cultural.",
        "horario_lines": B1_HORARIO_LINES, "updated_at": "2025-11-25", **kml_data,
    }
    b10_suspended = {
        "system": "troncal", "slug": "b10-suspendida", "label": "B10 (SUSPENDIDA)",
        "suspended": True, "route_code": "B10", "detail_url": "...",
        "recorrido_text": "", "horario_lines": [], "updated_at": None,
        "shape_coordinates": [], "stops": [],
    }

    path = tmp_path / "troncal_routes.jsonl"
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in [b1, b10_suspended]), encoding="utf-8"
    )
    return [path]


def test_build_stops_from_real_route_data(route_jsonl):
    stops = build_stops(route_jsonl)
    assert len(stops) == 13
    assert set(stops["stop_id"]) == {f"stop_{c}" for c in
        ["100", "101", "102", "103", "104", "105", "106", "107", "108", "109", "110", "201", "202"]}


def test_build_routes_excludes_suspended_by_default(route_jsonl):
    routes = build_routes(route_jsonl)
    assert list(routes["route_short_name"]) == ["B1"]
    assert routes.iloc[0]["route_long_name"] == "Portal de Soledad - Est. Parque Cultural del Caribe"


def test_build_routes_can_include_suspended(route_jsonl):
    routes = build_routes(route_jsonl, include_suspended=True)
    assert set(routes["route_short_name"]) == {"B1", "B10"}


def test_build_shapes_has_one_shape_for_b1(route_jsonl):
    shapes = build_shapes(route_jsonl)
    assert shapes["shape_id"].nunique() == 1
    assert len(shapes) == 23


def test_build_trips_creates_one_trip_per_service_window(route_jsonl):
    trips, stop_times, _frequencies = build_trips_stop_times_frequencies(route_jsonl)
    assert len(trips) == 3  # weekday, saturday, sunday
    assert set(trips["service_id"]) == {WEEKDAY, SATURDAY, SUNDAY}
    assert (stop_times.groupby("trip_id").size() == 13).all()  # all 13 stops on every trip


def test_build_trips_uses_real_headways_for_matched_troncal_route(route_jsonl):
    """B1 IS in the troncal frequency reference table -- 3 weekday bands,
    3 Saturday bands, 2 Sunday bands (see config/troncal_frequencies.yml).
    None of its frequencies.txt rows should be the placeholder.
    """
    _, _, frequencies = build_trips_stop_times_frequencies(route_jsonl)
    assert len(frequencies) == 3 + 3 + 2
    assert (frequencies["headway_secs"] != 9999).all()

    weekday_rows = frequencies[frequencies["trip_id"].str.endswith("_weekday")]
    assert list(weekday_rows["headway_secs"]) == [4 * 60, 7 * 60, 4 * 60]


def test_build_trips_falls_back_to_placeholder_for_unmatched_route(tmp_path):
    unmatched = {
        "system": "troncal", "slug": "z9", "label": "Z9", "suspended": False,
        "route_code": "Z9",  # not a real route code, not in the reference table
        "detail_url": "...", "recorrido_text": "", "updated_at": None,
        "horario_lines": ["Lunes a viernes: de 5:00 a.m. a 6:00 p.m."],
        "shape_coordinates": [[0.0, 0.0], [0.1, 0.1]],
        "stops": [
            {"cod_parada": "1", "nombre": "A", "secuencia": 1, "estado": "ACTIVO", "lat": 0.0, "lon": 0.0},
            {"cod_parada": "2", "nombre": "B", "secuencia": 2, "estado": "ACTIVO", "lat": 0.1, "lon": 0.1},
        ],
    }
    path = tmp_path / "troncal_routes.jsonl"
    path.write_text(json.dumps(unmatched, ensure_ascii=False), encoding="utf-8")

    _, _, frequencies = build_trips_stop_times_frequencies([path])
    assert len(frequencies) == 1
    assert frequencies.iloc[0]["headway_secs"] == 9999


def test_build_trips_uses_real_headways_for_matched_alimentadora_route_every_day(tmp_path):
    """A1-2 IS in the alimentadora frequency reference table for all three
    service days (each a single all-day band) -- every one of its
    frequencies.txt rows should carry the real per-day headway, not the
    placeholder.
    """
    kml_data = parse_kml(FIXTURE.read_text(encoding="utf-8"))  # reuse B1's stops/shape as a stand-in
    a1_2 = {
        "system": "alimentadora", "slug": "a1-2-carrera-ocho", "label": "A1-2 Carrera Ocho",
        "suspended": False, "route_code": "A1-2 Carrera Ocho",
        "detail_url": "https://transmetro.gov.co/sistema/rutas_alimentadoras/a1-2-carrera-ocho/",
        "recorrido_text": "", "updated_at": None,
        "horario_lines": [
            "Lunes a viernes: de 5:10 a.m. a 10:13 p.m.",
            "Sábados: de 5:15 a.m. a 10:14 p.m.",
            "Domingos y festivos: de 6:00 a.m. a 9:16 p.m.",
        ],
        **kml_data,
    }
    path = tmp_path / "alimentadora_routes.jsonl"
    path.write_text(json.dumps(a1_2, ensure_ascii=False), encoding="utf-8")

    _, _, frequencies = build_trips_stop_times_frequencies([path])
    assert len(frequencies) == 3  # one band per day, all single-band routes
    by_trip = frequencies.set_index(frequencies["trip_id"].str.rsplit("_", n=1).str[-1])
    assert by_trip.loc["weekday", "headway_secs"] == 12 * 60
    assert by_trip.loc["saturday", "headway_secs"] == 12 * 60
    assert by_trip.loc["sunday", "headway_secs"] == 12 * 60
    assert (by_trip["headway_secs"] != 9999).all()


def test_parse_horario_lines_handles_real_b1_text():
    windows = parse_horario_lines(B1_HORARIO_LINES)
    assert windows == [
        (WEEKDAY, "05:00:00", "18:22:00"),
        (SATURDAY, "05:00:00", "19:22:00"),
        (SUNDAY, "05:30:00", "18:22:00"),
    ]


def test_parse_horario_lines_skips_na_weekend_only_route():
    """A9-4 (a weekends-only feeder route) has no weekday service at all --
    "Lunes a viernes: N/A" -- which should be skipped, not raise, leaving
    just the two real windows.
    """
    lines = [
        "Lunes a viernes: N/A",
        "Sábados: de 5:10 p.m. a 9:30 p.m.",
        "Domingos y festivos: de 6:00 a.m. a 8:30 p.m.",
    ]
    windows = parse_horario_lines(lines)
    assert windows == [
        (SATURDAY, "17:10:00", "21:30:00"),
        (SUNDAY, "06:00:00", "20:30:00"),
    ]
