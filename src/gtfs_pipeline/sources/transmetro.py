"""Extractor for Transmetro's own route pages (troncales + alimentadoras).

FETCHING MECHANISM -- this matters and isn't the obvious choice, and has
gone through two wrong turns already worth knowing about before touching
this code again:

  1. First attempt: plain `requests`, even with full browser headers --
     404'd. Looked like bot-blocking at first.
  2. Second attempt: switched to Playwright (a real, scriptable Chromium)
     doing `page.goto()` directly on each URL -- STILL 404'd, with the
     exact same response every time: plain nginx, no WAF/Cloudflare
     signature, no bot-challenge, just a literal file-not-found. That
     ruled out bot-blocking entirely: transmetro.gov.co is a client-side-
     rendered React app whose server has no fallback rewrite rule for its
     own client-side routes -- `/sistema/rutas_troncales/` isn't a real
     file, so ANY fresh, direct HTTP request to it 404s, script or real
     browser alike. The rendered HTML pasted into the conversation this
     was built from was captured by clicking through the site from `/`,
     which changes the URL via the SPA's own client-side router (a
     History API pushState) WITHOUT a new server request -- not by
     loading that URL fresh, which is exactly what `page.goto()` does.

  3. What actually works: load the site root ONLY (`base_url` itself --
     the one path guaranteed to be a real file nginx can serve), then
     simulate real navigation by clicking the actual `<a>` elements
     already present in the rendered DOM, exactly like a real user would.
     That lets the SPA's own router handle routing client-side, so no
     further real HTTP request ever hits one of the paths nginx can't
     serve directly. Every "page load" after the first is a Playwright
     click + a wait for the DOM to settle, never a second `page.goto()`
     to a deep path.

The three-step fetch, updated for that constraint:

  1. Load `base_url`, click through to the listing page (e.g.
     /sistema/rutas_troncales/) via its real nav-menu link. Lists every
     route as a link to /sistema/rutas_<system>/<slug>/, inside an
     accordion whose label also flags suspended routes, e.g.
     "B10 (SUSPENDIDA)".
  2. Click through to each route's own detail page (from the listing page,
     going `page.go_back()` between routes rather than re-navigating from
     scratch). Each detail page embeds a *public* Google My Maps layer (a
     `mid` in the iframe src) and gives real text: an ordered, human-
     readable stop list ("Recorrido") and actual weekday / Saturday /
     Sunday operating windows ("Horario de rutas").
  3. That My Maps layer is itself fetchable as KML:
     https://www.google.com/maps/d/kml?mid=<mid>&forcekml=1
     For every route inspected so far, the KML contains BOTH the route
     line (a LineString) AND individually coded, sequenced stop points
     (each Placemark's ExtendedData has COD_PARADA / SECUENCIA_ /
     NOMBRE_PAR / LATITUD / LONGITUD / ESTADO). This KML -- not the HTML --
     is the real source of truth for shapes.txt and stops.txt; the HTML
     pages are only needed for metadata and to discover each route's `mid`.
     Unlike steps 1-2, this fetch IS a plain, direct request (a plain
     `requests` call, see below) since it's Google's URL, not Transmetro's
     broken one.

discover_routes_from_html() and parse_route_detail_html() (below) parse
whatever rendered HTML they're handed and don't care how it arrived, so
neither needed to change across any of this -- only the navigation
mechanism in the class above them did.

The KML fetch is NOT a Transmetro page at all -- it's a plain static file
from Google's My Maps export endpoint, needs no JS execution, and isn't
subject to any of the above -- so it still uses a plain `requests` session
(self.session, from BaseSource), not Playwright.

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
from xml.etree import ElementTree as ET

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import Page, sync_playwright

from .base import USER_AGENT, BaseSource

logger = logging.getLogger(__name__)

REQUEST_DELAY_SECONDS = 1.0  # be polite -- this is a small municipal site
PAGE_LOAD_TIMEOUT_MS = 30_000
KML_NS = "{http://www.opengis.net/kml/2.2}"
KML_NAMESPACES = {"kml": "http://www.opengis.net/kml/2.2"}
MID_RE = re.compile(r"[?&]mid=([^&\"']+)")


class TransmetroRouteSource(BaseSource):
    """kind: transmetro_routes. Config keys used: base_url, listing_path, system."""

    def fetch(self) -> Path:
        base_url = self.spec.raw["base_url"]
        listing_path = self.spec.raw["listing_path"]
        system = self.spec.raw["system"]  # "troncal" | "alimentadora"
        self._base_url = base_url  # used by _recover_to_listing() if go_back() ever can't get us back
        self._listing_path = listing_path

        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            try:
                page = browser.new_page(user_agent=USER_AGENT)
                route_links = self._discover_routes(page, base_url, listing_path)
                logger.info("found %d %s route(s) via %s", len(route_links), system, listing_path)

                records = []
                for slug, label in route_links:
                    try:
                        records.append(self._scrape_route(page, slug, label, system))
                    except Exception as exc:  # noqa: BLE001 -- one bad route shouldn't kill the whole fetch
                        logger.warning("failed to scrape %s: %s", slug, exc)
                        records.append(
                            {
                                "system": system, "slug": slug, "label": label,
                                "suspended": is_suspended(slug, label),
                                "detour": has_detour(label),
                                "error": str(exc),
                            }
                        )
                    time.sleep(REQUEST_DELAY_SECONDS)
            finally:
                browser.close()

        lines = "\n".join(json.dumps(r, ensure_ascii=False) for r in records)
        return self._write_text(lines)

    def _discover_routes(self, page: Page, base_url: str, listing_path: str) -> list[tuple[str, str]]:
        """Returns (slug, label) for every route in the "Selecciona la ruta"
        accordion, e.g. ("a3-40-villa-sol-suspendida", "A3-4  Villa Sol").
        Parsing logic lives in discover_routes_from_html() below, which
        takes rendered HTML and is unit-tested against saved pages with no
        browser involved -- this method's only job is getting there via
        real clicks (see the module docstring for why a direct `page.goto`
        on the listing path itself 404s).
        """
        page.goto(base_url, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT_MS)
        # NOT wait_until="networkidle" -- this page loads Google Analytics,
        # AdSense, and the UserWay accessibility widget, all of which keep
        # making background requests more or less indefinitely, so
        # "networkidle" reliably times out here (confirmed against a real
        # CI run) even once the actual app has long since rendered. Every
        # wait in this class waits for a specific element instead of a
        # network-quiescence heuristic, for the same reason.
        page.get_by_role("button", name="Mi Sistema").wait_for(state="visible", timeout=PAGE_LOAD_TIMEOUT_MS)
        self._click_nav_link(page, listing_path)
        self._expand_accordion_if_needed(page)
        return discover_routes_from_html(page.content())

    def _click_nav_link(self, page: Page, href_prefix: str) -> None:
        """The target link ("Rutas Troncales" / "Rutas Alimentadoras")
        lives inside the "Mi Sistema" Bootstrap dropdown, hidden until that
        toggle is clicked. Matched by accessible role+name rather than id:
        the page reuses the same id ("navbarDropdown") across several
        unrelated nav toggles -- a markup bug on the site itself -- so id
        selectors are ambiguous here even though they'd normally be exact.
        """
        page.get_by_role("button", name="Mi Sistema").click()
        link = page.locator(f'a[href^="{href_prefix}"]').first
        link.wait_for(state="visible", timeout=PAGE_LOAD_TIMEOUT_MS)
        link.click()
        # confirms the client-side route actually changed and the listing
        # page's own accordion toggle has rendered -- see the goto() above
        # for why this isn't a wait_for_load_state("networkidle") call
        page.get_by_role("button", name="Selecciona la ruta").wait_for(state="visible", timeout=PAGE_LOAD_TIMEOUT_MS)

    def _expand_accordion_if_needed(self, page: Page) -> None:
        """Confirmed against real pasted HTML for both systems: the
        troncal listing page renders its "Selecciona la ruta" accordion
        already expanded (class "show" present) on its very first mount;
        the alimentadora one renders it collapsed. The toggle button flips
        state either way, so this only clicks it when the body isn't
        already visible, rather than risking closing an already-open
        accordion.

        NOT a one-time setup step: also confirmed against a real run that
        the expanded state does NOT survive a go_back() to the listing
        page -- even troncal's comes back collapsed after the first
        route's back-navigation, even though it started expanded. So this
        gets called again after every go_back() in _scrape_route(), not
        just once from _discover_routes() when the listing page first
        loads.
        """
        body = page.locator("#collapseOne")
        if body.count() and not body.first.is_visible():
            page.get_by_role("button", name="Selecciona la ruta").click()
            body.first.wait_for(state="visible", timeout=PAGE_LOAD_TIMEOUT_MS)

    def _scrape_route(self, page: Page, slug: str, label: str, system: str) -> dict:
        """Clicks the specific route's link from the (already-open) listing
        page -- never a direct `page.goto` to its URL, same reasoning as
        _discover_routes. Always navigates back to the listing page before
        returning, but ONLY if the click actually started a navigation --
        the `navigated` flag matters here: if the click itself fails (link
        not found, timeout), nothing moved and we're already back on the
        listing page, so go_back() would incorrectly step past it.

        The return-to-listing step is delegated to _return_to_listing(),
        which NEVER raises -- confirmed against a real run: a scrape can
        fully succeed and then have go_back() hang/fail in this method's
        `finally` block, and a `finally` block that raises silently
        DISCARDS an already-successful `return record` from the `try`
        above it, replacing it with the `finally`'s exception instead. A
        route that scraped correctly must never be reported as a failure
        just because navigating away from it afterward had trouble.
        """
        navigated = False
        try:
            page.locator(f'a[href*="/{slug}/"]').first.click()
            navigated = True
            # confirms the detail page actually rendered -- h2.azul-lt is
            # the route's own title, present on every detail page (see
            # both real fixtures); not a networkidle wait, see the
            # _discover_routes docstring for why
            page.locator("h2.azul-lt").wait_for(state="visible", timeout=PAGE_LOAD_TIMEOUT_MS)

            detail_url = page.url
            parsed = parse_route_detail_html(page.content())
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
                try:
                    record.update(self._fetch_kml(record["mid"]))
                except requests.HTTPError as exc:
                    # confirmed against a real run: suspended routes'
                    # My Maps layers can 404 (likely deleted once the
                    # route stopped operating) -- that's a real, expected
                    # possibility for suspended routes specifically, not a
                    # reason to discard everything else this route's page
                    # scraped successfully (label, schedule text, etc.)
                    logger.warning("KML fetch failed for slug=%s: %s", slug, exc)
                    record["kml_error"] = str(exc)
            else:
                record["kml_error"] = "no `mid` found in the route's map iframe -- no geodata for this route"

            return record
        finally:
            if navigated:
                self._return_to_listing(page)

    def _return_to_listing(self, page: Page) -> None:
        """Gets back to a working listing page after a route detail page.
        Never raises: any trouble here must not look like the route we
        just scraped failed (see _scrape_route's docstring). Two layers:
        1. The normal path -- go_back(wait_until="commit"), the lightest
           possible wait, then confirm via the same explicit content wait
           used everywhere else in this class. NOT the default
           wait_until="load": confirmed against a real run that this
           SPA's client-side history navigation can hang waiting for a
           "load" event for ~30s, since no real page reload happens for
           it -- "commit" only waits for the navigation to have started,
           which is enough given the explicit wait_for() right after it.
        2. If that still doesn't leave us on a working listing page for
           any reason, a last-resort recovery: start over from base_url
           and click through again, exactly like the first navigation in
           _discover_routes(). Slower, but guarantees the NEXT route in
           the loop still gets a clean starting state rather than
           inheriting whatever broken state this one left behind.
        """
        try:
            page.go_back(wait_until="commit", timeout=PAGE_LOAD_TIMEOUT_MS)
            page.get_by_role("button", name="Selecciona la ruta").wait_for(
                state="visible", timeout=PAGE_LOAD_TIMEOUT_MS
            )
            self._expand_accordion_if_needed(page)
        except Exception as exc:  # noqa: BLE001 -- must not propagate, see docstring
            logger.warning("go_back to the listing page had trouble (%s) -- recovering from base_url", exc)
            self._recover_to_listing(page)

    def _recover_to_listing(self, page: Page) -> None:
        try:
            page.goto(self._base_url, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT_MS)
            page.get_by_role("button", name="Mi Sistema").wait_for(state="visible", timeout=PAGE_LOAD_TIMEOUT_MS)
            self._click_nav_link(page, self._listing_path)
            self._expand_accordion_if_needed(page)
        except Exception as exc:  # noqa: BLE001 -- still must not propagate; the next route's own click will fail loudly if this really didn't work
            logger.warning("recovery navigation to the listing page also failed: %s", exc)

    def _fetch_kml(self, mid: str) -> dict:
        # plain requests here on purpose -- see the module docstring for why
        # this one fetch doesn't need Playwright.
        kml_url = f"https://www.google.com/maps/d/kml?mid={mid}&forcekml=1"
        resp = self.session.get(kml_url, timeout=30)
        resp.raise_for_status()

        # NOT resp.text: requests decides encoding from the HTTP
        # Content-Type header (or its own guess when that's absent/vague),
        # ignoring the KML document's own `<?xml ... encoding="UTF-8"?>`
        # declaration entirely -- a well-known gotcha. If Google's response
        # doesn't send an explicit charset and requests guesses wrong, it
        # decodes with errors='replace', which is the exact mechanism that
        # inserts U+FFFD -- a real gtfs-validator run found several stop
        # names with U+FFFD where an "ñ" or a dash should be, and it was
        # unclear whether that came from here or was already present in
        # Google/Transmetro's stored data (no way to tell from the Unicode
        # replacement character alone, and this pipeline can't reach
        # google.com from its own dev sandbox to test directly). Decoding
        # explicitly as UTF-8 -- what the document itself declares, and
        # what KML/XML from Google actually is -- removes requests'
        # guessing from the picture entirely. If U+FFFD still shows up
        # after this, that's real proof it's in the raw bytes Google
        # serves, not introduced by this fetch.
        return parse_kml(resp.content.decode("utf-8", errors="replace"))


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
