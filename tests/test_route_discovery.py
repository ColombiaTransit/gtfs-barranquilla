"""Tests discover_routes_from_html(), is_suspended(), and has_detour()
against the real listing pages pasted into the conversation this was built
from -- not synthetic HTML, so this pins the parser to the site's actual
(and, it turns out, inconsistent) markup rather than an assumption of it.
"""
from __future__ import annotations

from pathlib import Path

from gtfs_pipeline.sources.transmetro import (
    discover_routes_from_html,
    has_detour,
    is_suspended,
    parse_route_detail_html,
)

TRONCAL_FIXTURE = Path(__file__).parent / "fixtures" / "rutas_troncales_listing.html"
ALIMENTADORA_FIXTURE = Path(__file__).parent / "fixtures" / "rutas_alimentadoras_listing.html"
TRONCAL_DETAIL_FIXTURE = Path(__file__).parent / "fixtures" / "troncal_route_detail_b1.html"
ALIMENTADORA_DETAIL_FIXTURE = Path(__file__).parent / "fixtures" / "alimentadora_route_detail.html"


def test_discover_routes_troncal_excludes_nav_links_and_gets_right_slugs():
    routes = discover_routes_from_html(TRONCAL_FIXTURE.read_text(encoding="utf-8"))
    slugs = [slug for slug, _ in routes]

    # the nav dropdown's self-links to the listing pages must NOT appear
    assert "rutas_troncales" not in slugs
    assert "rutas_alimentadoras" not in slugs

    # real route slugs, correctly split BEFORE the #fragment
    assert "b1" in slugs
    assert "b10-suspendida" in slugs
    assert len(routes) == 12  # every route link in the fixture


def test_discover_routes_alimentadora_excludes_nav_links():
    routes = discover_routes_from_html(ALIMENTADORA_FIXTURE.read_text(encoding="utf-8"))
    slugs = [slug for slug, _ in routes]

    assert "rutas_troncales" not in slugs
    assert "rutas_alimentadoras" not in slugs
    assert "a8-1-paraiso" in slugs
    assert "a3-40-villa-sol-suspendida" in slugs


def test_is_suspended_catches_status_in_either_slug_or_label():
    # label says SUSPENDIDA
    assert is_suspended("b10-suspendida", "B10 (SUSPENDIDA)") is True
    # label doesn't mention it at all -- only the slug does
    assert is_suspended("a3-40-villa-sol-suspendida", "A3-4  Villa Sol") is True
    # "suspendida temporalmente" wording, slug doesn't say it
    assert is_suspended("a4-1-malambo", "A4-1 Malambo  (suspendida temporalmente)") is True
    # a normal active route
    assert is_suspended("b1", "B1") is False


def test_has_detour_is_independent_of_suspended():
    assert has_detour("A8-1 Paraíso (opera con desvío)") is True
    assert has_detour("B1") is False
    # a detour route is NOT suspended, and a suspended route doesn't need to mention detour
    assert is_suspended("a8-1-paraiso", "A8-1 Paraíso (opera con desvío)") is False


def test_parse_route_detail_troncal_template():
    parsed = parse_route_detail_html(TRONCAL_DETAIL_FIXTURE.read_text(encoding="utf-8"))
    assert parsed["route_code"] == "B1"
    assert parsed["mid"] == "1GJlP__TsDxbyUnVNQ9iFN1Zda0IbXRY"
    assert parsed["recorrido_text"].startswith("Servicio corriente que hace su recorrido")
    assert len(parsed["horario_lines"]) == 3
    assert parsed["updated_at"] == "2025-11-25T20:22:24.856Z"


def test_parse_route_detail_alimentadora_template():
    """The alimentadora template differs in two real ways from troncal:
    the schedule container is class "horario-sitio" (not "...Troncal"),
    and the route description is an untitled paragraph, not a card titled
    "Recorrido". Both must still be extracted.
    """
    parsed = parse_route_detail_html(ALIMENTADORA_DETAIL_FIXTURE.read_text(encoding="utf-8"))
    assert parsed["route_code"] == "A9-4 Carrera 46 / fines de semana"
    assert parsed["mid"] == "1jOpXLwdtweVYjKZONKtlRNyZ9bAS8k8"
    assert parsed["recorrido_text"].startswith("Este servicio alimentador opera")
    assert len(parsed["horario_lines"]) == 3
    assert "N/A" in parsed["horario_lines"][0]  # this route has no weekday service at all
    assert parsed["updated_at"] == "2025-11-20T15:17:06.837Z"
