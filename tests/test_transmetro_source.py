"""Tests parse_kml() against the actual B1.kml pulled from Transmetro's My
Maps export -- not a synthetic fixture, so this pins the parser to the
real structure (Folder-per-shape, Folder-per-stops, ExtendedData field
names) rather than an assumption of it.
"""
from __future__ import annotations

from pathlib import Path

from gtfs_pipeline.sources.transmetro import parse_kml

FIXTURE = Path(__file__).parent / "fixtures" / "B1.kml"


def test_parse_kml_extracts_shape_and_stops():
    result = parse_kml(FIXTURE.read_text(encoding="utf-8"))

    assert len(result["shape_coordinates"]) == 23  # coordinate count in the LineString
    lon, lat = result["shape_coordinates"][0]
    assert lon == -74.799076
    assert lat == 10.90811

    assert len(result["stops"]) == 13
    first = result["stops"][0]
    assert first["cod_parada"] == "100"
    assert first["nombre"] == "Portal de Soledad"
    assert first["secuencia"] == 1
    assert first["estado"] == "ACTIVO"
    assert first["lat"] == 10.907941
    assert first["lon"] == -74.800165


def test_parse_kml_stops_are_in_sequence_order():
    result = parse_kml(FIXTURE.read_text(encoding="utf-8"))
    sequences = [s["secuencia"] for s in result["stops"]]
    assert sequences == sorted(sequences)
