"""Tests parse_kml() against the actual B1.kml pulled from Transmetro's My
Maps export -- not a synthetic fixture, so this pins the parser to the
real structure (Folder-per-shape, Folder-per-stops, ExtendedData field
names) rather than an assumption of it.
"""
from __future__ import annotations

from pathlib import Path
from unittest import mock

import requests

from gtfs_pipeline.config import SourceSpec
from gtfs_pipeline.sources.transmetro import TransmetroRouteSource, parse_kml

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


def test_fetch_kml_still_uses_plain_requests_not_playwright():
    """The KML fetch (step 3) is a plain static file from Google's My Maps
    export endpoint, not a Transmetro page -- it must keep using the
    requests session from BaseSource, not a browser, since that's the
    whole point of keeping it separate from the Playwright-driven HTML
    fetch (see the module docstring). This pins that down: mocking
    self.session.get should be enough to control _fetch_kml() end to end,
    with no browser involved at all.
    """
    spec = SourceSpec(name="test", kind="transmetro_routes", output_file="out.jsonl", raw={})
    source = TransmetroRouteSource(spec)

    fake_response = mock.Mock()
    fake_response.text = FIXTURE.read_text(encoding="utf-8")
    fake_response.raise_for_status = mock.Mock()

    with mock.patch.object(source.session, "get", return_value=fake_response) as mocked_get:
        result = source._fetch_kml("some_mid_value")

    mocked_get.assert_called_once()
    called_url = mocked_get.call_args.args[0]
    assert "some_mid_value" in called_url
    assert "google.com/maps/d/kml" in called_url
    assert len(result["stops"]) == 13


def test_fetch_kml_propagates_http_errors():
    spec = SourceSpec(name="test", kind="transmetro_routes", output_file="out.jsonl", raw={})
    source = TransmetroRouteSource(spec)

    fake_response = mock.Mock()
    fake_response.raise_for_status.side_effect = requests.HTTPError("404")

    with mock.patch.object(source.session, "get", return_value=fake_response):
        try:
            source._fetch_kml("bad_mid")
            raise AssertionError("expected HTTPError to propagate")
        except requests.HTTPError:
            pass
