"""Extractor for Transmetro's own route pages (troncales + alimentadoras).

Three-step fetch per system (troncal / alimentadora):

  1. The listing page (e.g. /sistema/rutas_troncales/) lists every route as
     a link to /sistema/rutas_<system>/<slug>/, inside an accordion whose
     label also flags suspended routes, e.g. "B10 (SUSPENDIDA)".
  2. Each route's own detail page embeds a *public* Google My Maps layer
     (a `mid` in the iframe src) and gives real text: an ordered,
     human-readable stop list ("Recorrido") and actual weekday / Saturday /
     Sunday operating windows ("Horario de rutas").
  3. That My Maps layer is itself fetchable as KML:
     https://www.google.com/maps/d/kml?mid=<mid>&forcekml=1
     For every route inspected so far, the KML contains BOTH the route
     line (a LineString) AND individually coded, sequenced stop points
     (each Placemark's ExtendedData has COD_PARADA / SECUENCIA_ /
     NOMBRE_PAR / LATITUD / LONGITUD / ESTADO). This KML -- not the HTML --
     is the real source of truth for shapes.txt and stops.txt; the HTML
     pages are only needed for metadata and to discover each route's `mid`.

NOTE: this has only been verified against the troncal listing + B1 detail
page (see the pages pasted into the conversation this was built from). The
alimentadora pages are assumed to share the same template (the troncal
page's own CSS already uses a shared ".map-alimentadora" class name), but
that assumption hasn't been checked against a real alimentadora page yet --
if `fetch(system="alimentadora")` fails, that's the first thing to check.

Writes one JSON object per route as JSON Lines (not per system), so
transform/ can build routes/stops/shapes/calendar straight from this file
without re-touching HTML or KML.
"""
from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from urllib.parse import urljoin
from xml.etree import ElementTree as ET

from bs4 import BeautifulSoup

from .base import BaseSource

logger = logging.getLogger(__name__)

REQUEST_DELAY_SECONDS = 1.0  # be polite -- this is a small municipal site
KML_NS = "{http://www.opengis.net/kml/2.2}"
KML_NAMESPACES = {"kml": "http://www.opengis.net/kml/2.2"}
MID_RE = re.compile(r"[?&]mid=([^&\"']+)")


class TransmetroRouteSource(BaseSource):
    """kind: transmetro_routes. Config keys used: base_url, listing_path, system."""

    def fetch(self) -> Path:
        base_url = self.spec.raw["base_url"]
        listing_path = self.spec.raw["listing_path"]
        system = self.spec.raw["system"]  # "troncal" | "alimentadora"

        listing_url = urljoin(base_url, listing_path)
        route_links = self._discover_routes(listing_url)
        logger.info("found %d %s route(s) on %s", len(route_links), system, listing_url)

        records = []
        for slug, label in route_links:
            detail_url = urljoin(listing_url, f"{slug}/")
            try:
                records.append(self._scrape_route(detail_url, slug, label, system))
            except Exception as exc:  # noqa: BLE001 -- one bad route shouldn't kill the whole fetch
                logger.warning("failed to scrape %s: %s", detail_url, exc)
                records.append(
                    {
                        "system": system, "slug": slug, "label": label,
                        "suspended": is_suspended(slug, label),
                        "detour": has_detour(label),
                        "error": str(exc),
                    }
                )
            time.sleep(REQUEST_DELAY_SECONDS)

        lines = "\n".join(json.dumps(r, ensure_ascii=False) for r in records)
        return self._write_text(lines)

    def _discover_routes(self, listing_url: str) -> list[tuple[str, str]]:
        """Returns (slug, label) for every route in the "Selecciona la ruta"
        accordion, e.g. ("a3-40-villa-sol-suspendida", "A3-4  Villa Sol").
        Public logic factored into discover_routes_from_html() below so it
        can be unit-tested against saved listing pages without a network
        call.
        """
        resp = self.session.get(listing_url, timeout=30)
        resp.raise_for_status()
        return discover_routes_from_html(resp.text)

    def _scrape_route(self, detail_url: str, slug: str, label: str, system: str) -> dict:
        resp = self.session.get(detail_url, timeout=30)
        resp.raise_for_status()
        parsed = parse_route_detail_html(resp.text)
        parsed["route_code"] = parsed["route_code"] or label  # fall back if the page has no h2 title

        record = {
            "system": system,
            "slug": slug,
            "label": label,
            "suspended": is_suspended(slug, label),
            "detour": has_detour(label),
            **parsed,
            "detail_url": detail_url,
            "shape_coordinates": [],
            "stops": [],
        }

        if record["mid"]:
            record.update(self._fetch_kml(record["mid"]))
        else:
            record["kml_error"] = "no `mid` found in the route's map iframe -- no geodata for this route"

        return record

    def _fetch_kml(self, mid: str) -> dict:
        kml_url = f"https://www.google.com/maps/d/kml?mid={mid}&forcekml=1"
        resp = self.session.get(kml_url, timeout=30)
        resp.raise_for_status()
        return parse_kml(resp.text)


def parse_route_detail_html(html: str) -> dict:
    """Pure function: one route's detail page HTML -> route metadata.
    Pulled out for the same reason as discover_routes_from_html() --
    testable against a saved page with no network.

    Troncal and alimentadora pages turn out to use different templates for
    two of these fields, both handled here:
      - the schedule/description container's class is "horario-sitioTroncal"
        on troncal pages but "horario-sitio" on alimentadora pages --
        matched with a substring attribute selector instead of either exact
        class name.
      - troncal pages give the route description as a card titled
        "Recorrido"; alimentadora pages give it as an untitled paragraph
        (no matching card-title at all) sitting above the schedule card --
        both are checked, titled card first.
    """
    soup = BeautifulSoup(html, "lxml")

    title_el = soup.select_one("h2.azul-lt")
    route_code = title_el.get_text(strip=True) if title_el else None

    map_iframe = soup.select_one(".map-alimentadora iframe")
    mid_match = MID_RE.search(map_iframe["src"]) if map_iframe and map_iframe.get("src") else None
    mid = mid_match.group(1) if mid_match else None

    recorrido_text, horario_lines, updated_at = None, [], None
    for card_body in soup.select('[class*="horario-sitio"] .card-body'):
        heading = card_body.select_one(".card-title")
        text_el = card_body.select_one(".card-text")

        if heading and "recorrido" in heading.get_text().lower():
            recorrido_text = text_el.get_text(strip=True) if text_el else None
        elif heading and "horario" in heading.get_text().lower():
            horario_lines = [li.get_text(strip=True) for li in card_body.select("li")]
            small = card_body.select_one("small")
            if small:
                m = re.search(r"Actualizado\s*(.+)", small.get_text(strip=True))
                updated_at = m.group(1) if m else small.get_text(strip=True)
        elif not heading and text_el and "azul-lt" in (text_el.get("class") or []) and recorrido_text is None:
            # alimentadora-style: an untitled description paragraph, not
            # wrapped in a "Recorrido"-titled card at all
            recorrido_text = text_el.get_text(strip=True)

    return {
        "route_code": route_code,
        "mid": mid,
        "recorrido_text": recorrido_text,
        "horario_lines": horario_lines,
        "updated_at": updated_at,
    }


def discover_routes_from_html(html: str) -> list[tuple[str, str]]:
    """Pure function version of route discovery -- takes a listing page's
    HTML and returns [(slug, label), ...]. Pulled out of the extractor so
    it can be unit-tested against a saved listing page with no network.

    Two things this has to get right that a naive "any link containing
    /sistema/rutas_" selector gets wrong:
      1. The href's `#fragment` must be stripped BEFORE splitting on `/`,
         not after -- otherwise something like ".../b1/#Rtroncal" yields
         "#Rtroncal" as the last path segment instead of "b1".
      2. The site's own nav menu links to the listing pages themselves
         (".../rutas_troncales/#rutas-troncales") also match a substring
         filter on "/sistema/rutas_" -- these must be excluded, not
         treated as routes.
    """
    soup = BeautifulSoup(html, "lxml")

    routes, seen_slugs = [], set()
    for a in soup.select("a[href]"):
        href = a["href"]
        if "/sistema/rutas_" not in href:
            continue
        slug = _slug_from_href(href)
        # a bare "rutas_troncales" / "rutas_alimentadoras" slug means the
        # link pointed at the listing page itself, not a route under it
        if not slug or slug.startswith("rutas_") or slug in seen_slugs:
            continue
        seen_slugs.add(slug)
        routes.append((slug, a.get_text(strip=True)))

    if not routes:
        raise RuntimeError(
            "No route links found in this listing page -- the site's markup "
            "may have changed; update discover_routes_from_html()."
        )
    return routes


def _slug_from_href(href: str) -> str:
    path = href.split("#", 1)[0]  # strip the fragment BEFORE splitting on "/"
    return path.rstrip("/").split("/")[-1]


def is_suspended(slug: str, label: str) -> bool:
    """True for both "(SUSPENDIDA)" in the visible label and a
    "-suspendida" suffix that only shows up in the URL slug -- the site is
    inconsistent about which one carries the status (e.g. A3-4 Villa Sol's
    slug says suspendida but its label doesn't), so both are checked.
    Matches SUSPENDIDA/SUSPENDIDO/SUSPENDIDAS via the shared stem.
    """
    return "SUSPENDID" in f"{slug} {label}".upper()


def has_detour(label: str) -> bool:
    """True for "(opera con desvío)" -- a route that's running, just on a
    temporary alternate path. Distinct from suspended: this route should
    still get trips built, just flagged for a human to notice the caveat.
    """
    return bool(re.search(r"desv[ií]o", label, re.IGNORECASE))


def parse_kml(kml_text: str) -> dict:
    """Pulls the route LineString and stop Placemarks out of a My Maps KML
    export. Public function (not just an internal method) so it can be
    unit-tested directly against a saved .kml fixture without needing
    network access.
    """
    root = ET.fromstring(kml_text)
    shape_coordinates: list[list[float]] = []
    stops: list[dict] = []

    for placemark in root.iter(f"{KML_NS}Placemark"):
        line = placemark.find("kml:LineString/kml:coordinates", KML_NAMESPACES)
        point = placemark.find("kml:Point/kml:coordinates", KML_NAMESPACES)

        if line is not None and line.text:
            for triplet in line.text.split():
                lon, lat, *_ = triplet.split(",")
                shape_coordinates.append([float(lon), float(lat)])

        elif point is not None and point.text:
            data = {
                d.get("name"): (d.findtext("kml:value", default="", namespaces=KML_NAMESPACES) or "").strip()
                for d in placemark.findall("kml:ExtendedData/kml:Data", KML_NAMESPACES)
            }
            lon_txt, lat_txt, *_ = point.text.strip().split(",")
            try:
                stops.append(
                    {
                        "cod_parada": data.get("COD_PARADA"),
                        "nombre": data.get("NOMBRE_PAR"),
                        "secuencia": int(data["SECUENCIA_"]) if data.get("SECUENCIA_") else None,
                        "estado": data.get("ESTADO"),
                        "lat": float(data.get("LATITUD") or lat_txt),
                        "lon": float(data.get("LONGITUD") or lon_txt),
                    }
                )
            except (TypeError, ValueError) as exc:
                logger.warning("skipping malformed stop Placemark: %s (%s)", data, exc)

    return {"shape_coordinates": shape_coordinates, "stops": stops}
