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
    fake_response.content = FIXTURE.read_bytes()
    fake_response.raise_for_status = mock.Mock()

    with mock.patch.object(source.session, "get", return_value=fake_response) as mocked_get:
        result = source._fetch_kml("some_mid_value")

    mocked_get.assert_called_once()
    called_url = mocked_get.call_args.args[0]
    assert "some_mid_value" in called_url
    assert "google.com/maps/d/kml" in called_url
    assert len(result["stops"]) == 13


def test_fetch_kml_decodes_as_utf8_explicitly_not_requests_guess():
    """_fetch_kml must use resp.content.decode("utf-8", ...), NOT
    resp.text -- requests picks .text's encoding from the HTTP
    Content-Type header (or its own guess), ignoring the KML document's
    own `<?xml ... encoding="UTF-8"?>` declaration entirely. If requests
    guessed wrong here, it would decode with errors='replace', which is
    the exact mechanism that inserts U+FFFD -- a real gtfs-validator run
    found that character in several stop names, and it was unclear
    whether requests' guessing was the cause. This test sets .text to
    something requests might have produced under a WRONG guessed encoding
    (garbage) while .content holds the real correct UTF-8 bytes, so it
    only passes if _fetch_kml genuinely reads .content, not .text.
    """
    spec = SourceSpec(name="test", kind="transmetro_routes", output_file="out.jsonl", raw={})
    source = TransmetroRouteSource(spec)

    fake_response = mock.Mock()
    fake_response.content = FIXTURE.read_bytes()
    fake_response.text = "not the real content -- would only be read on a bug"
    fake_response.raise_for_status = mock.Mock()

    with mock.patch.object(source.session, "get", return_value=fake_response):
        result = source._fetch_kml("some_mid_value")

    assert result["stops"][0]["nombre"] == "Portal de Soledad"


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


def test_scrape_route_survives_a_kml_404_without_losing_the_rest_of_the_record():
    """Confirmed against a real run: a suspended route's My Maps layer can
    404 (the layer was likely deleted once the route stopped operating).
    That must degrade to a `kml_error` field on an otherwise-complete
    record -- everything the route's own page scraped successfully
    (route_code, recorrido_text, horario_lines, mid) -- not discard the
    whole route the way letting the HTTPError propagate would.
    """
    spec = SourceSpec(name="test", kind="transmetro_routes", output_file="out.jsonl", raw={})
    source = TransmetroRouteSource(spec)

    fake_page = mock.MagicMock()
    fake_page.url = "https://transmetro.gov.co/sistema/rutas_troncales/b10-suspendida/"

    parsed = {
        "route_code": "B10", "mid": "some_mid",
        "recorrido_text": "Servicio suspendido.", "horario_lines": [], "updated_at": None,
    }
    with (
        mock.patch("gtfs_pipeline.sources.transmetro.parse_route_detail_html", return_value=parsed),
        mock.patch.object(source, "_fetch_kml", side_effect=requests.HTTPError("404 Client Error")),
        mock.patch.object(source, "_return_to_listing"),  # not under test here
    ):
        record = source._scrape_route(fake_page, "b10-suspendida", "B10 (SUSPENDIDA)", "troncal")

    assert record["route_code"] == "B10"
    assert record["recorrido_text"] == "Servicio suspendido."
    assert "404" in record["kml_error"]
    assert "shape_coordinates" in record  # still present (empty), not just missing from a discarded record
