# gtfs-barranquilla

A pipeline that downloads Transmetro (Barranquilla, Colombia) transit data
and builds a [GTFS](https://gtfs.org/schedule/reference/) static feed from
it.

## Why this exists

Transmetro doesn't publish an official GTFS feed. This pipeline scrapes
[transmetro.gov.co](https://transmetro.gov.co)'s own route pages — each
route embeds a *public Google My Maps layer* that, fetched as KML, turns
out to contain real coordinates for both the route shape and every
individually coded/sequenced stop (not just a picture). See
`src/gtfs_pipeline/sources/transmetro.py` for the full three-step fetch
(listing page → route page → KML export) and why the KML, not the HTML, is
the actual source of truth.

## Status

**This is a working pipeline against real, verified data for both the
troncal (trunk) and alimentadora (feeder) route systems — not a
placeholder scaffold.** What's real vs. still approximate:

| Piece | State |
|---|---|
| Repo / pipeline structure | done |
| `stops.txt` | real — deduped by stop code (`COD_PARADA`) across routes, from KML |
| `routes.txt` | real — code, origin/destination, description, all scraped |
| `shapes.txt` | real — actual route line coordinates from each route's KML |
| `calendar.txt` | real day-of-week pattern (weekday/Saturday/Sunday); date *range* is an arbitrary 1-year window since no upstream source gives calendar validity dates |
| `calendar_dates.txt` | real — Colombian public holidays (via the `holidays` package, current + next year, "Ley Emiliani" Monday-shifting included) are swapped onto the `sunday` service pattern, matching every route's own "Domingo y festivos" schedule text |
| `trips.txt` / `stop_times.txt` | real operating **windows** (start/end time) per route from scraped "Horario de rutas" text; stop-to-stop timing within that window is still an evenly-spaced placeholder — no inter-stop travel time source exists yet |
| `frequencies.txt` | start/end times are real; **headway is real for both troncal and alimentadora routes matched in `config/troncal_frequencies.yml` / `config/alimentadora_frequencies.yml`, on all three service days** (six current PDFs from a Jan 2024 rollout, plus one 2018 news article specifically for S40's weekday headway — the only route/day with no current source at all; see each file's header for exact provenance); anything still unmatched falls back to a placeholder (`9999`s) |
| Alimentadora (feeder) routes | **verified** — listing page and a real detail page (A9-4) both inspected. Two template differences from troncal pages, both handled: the schedule container's CSS class differs, and the route description is an untitled paragraph instead of a titled "Recorrido" card. Some feeder routes have no weekday service at all ("N/A") — handled by skipping that window, not building a weekday trip for them |
| GitHub Actions (scheduled build, CI, release) | done — validation now runs the official [MobilityData gtfs-validator](https://github.com/MobilityData/gtfs-validator) (Java, via its Docker image) against the built feed, not a hand-rolled Python check |

Spec validation happens in CI (see `.github/workflows/build-gtfs.yml`), not
as a command in this CLI — there's no `gtfsbaq validate`. That workflow
fails the build on any ERROR-severity notice and uploads the full
JSON/HTML report as a build artifact either way, so a failed run still
tells you why.

## Pipeline stages

```
config/sources.yml
        │
        ▼
1. fetch      src/gtfs_pipeline/sources/*      → data/raw/       (whatever shape each source gives you)
2. transform  src/gtfs_pipeline/transform/*     → data/interim/*.csv   (GTFS-shaped tidy tables)
3. build      src/gtfs_pipeline/build.py        → data/gtfs/gtfs.zip
```

Each stage only depends on the previous stage's output on disk, so any one
of them can be re-run alone while debugging. GTFS spec validation is a
separate CI step, not part of this pipeline (see above).

## Getting started

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

gtfsbaq fetch       # download raw sources into data/raw/
gtfsbaq transform   # build GTFS-shaped tables into data/interim/
gtfsbaq build       # zip them into data/gtfs/gtfs.zip
# or just:
gtfsbaq all

# to validate locally the same way CI does (requires Docker):
docker run --rm -v "$(pwd)/data/gtfs:/gtfs" -v "$(pwd)/validation-report:/report" \
  ghcr.io/mobilitydata/gtfs-validator:latest -i /gtfs/gtfs.zip -o /report --country_code CO
```

## Adding or fixing a source

Sources are declared in `config/sources.yml`, not hardcoded — both current
sources use the same extractor `kind: transmetro_routes`
(`src/gtfs_pipeline/sources/transmetro.py`). To add a genuinely different
kind of source later, subclass `BaseSource` and register it in
`sources/__init__.py`.

**Known gap:** `alimentadora_routes` and `troncal_routes` both use the
same extractor and are verified against real pages (see the Status table),
but if the site's markup changes again, check the selectors in
`sources/transmetro.py` (`_discover_routes`, `parse_route_detail_html`)
against the live HTML before assuming the code itself is broken —
troncal and alimentadora pages already use two different template
variants for their schedule section, so a third variant showing up isn't
implausible.

**Known gap:** a small number of route/day combinations still have no
matching reference data at all and fall back to the placeholder — e.g.
Saturday/Sunday for S40, where even the 2018 article that filled its
weekday figure has nothing. `PLACEHOLDER_HEADWAY_SECS` and
`DWELL_SECONDS_PER_STOP` in `transform/trips_and_stop_times.py` mark
exactly where more real data would plug in.

**Not yet used, but scraped and available:** alimentadora pages also list
a textual, unordered-by-coordinate "Paraderos" stop list (street
addresses/landmarks) separate from the KML's coded stop points — this
could be useful for cross-checking stop names/order against the KML data,
but isn't scraped or used yet.

## Project layout

```
config/sources.yml                    source registry + static GTFS fields (agency, feed_info)
config/alimentadora_frequencies.yml   real headways, alimentadora routes, all 3 service days (see its own header)
config/troncal_frequencies.yml        real headways, troncal routes, all 3 service days (see its own header)
src/gtfs_pipeline/
  config.py                     paths + config loading
  sources/
    transmetro.py                stage 1: listing page -> route page -> KML, per route
  transform/                    stage 2: raw JSONL -> GTFS-shaped tables
    _routes_io.py                 shared "read the scraped route JSONL" helper
    horario.py                    parses "Lunes a viernes: de 5:00 a.m. a 6:22 p.m." into GTFS time windows
    calendar_dates.py             swaps Colombian public holidays onto the Sunday service pattern
    frequency_reference.py        matches scraped route codes against the real per-day headway tables
    stops.py / routes.py / shapes.py / calendar.py / trips_and_stop_times.py
  build.py                      stage 3: tables -> gtfs.zip
  cli.py                        `gtfsbaq` command
tests/
  fixtures/                       real HTML/KML pulled from the live site -- every test below is pinned to real data, not synthetic markup
  test_transmetro_source.py        KML parsing (parse_kml) against the real B1.kml
  test_route_discovery.py          route discovery + suspended/detour detection against real listing pages, and per-day-template detail-page parsing (troncal vs alimentadora)
  test_transform.py                end-to-end: stops/routes/shapes/trips/frequencies from real route records
  test_frequency_reference.py      route-code matching + real headway lookups for both systems, all 3 service days
  test_calendar_dates.py           holiday calendar_dates.txt against real Colombian holiday dates
  test_build.py                    build.py assembles a well-formed zip from fixture tables
.github/workflows/
  ci.yml                        lint + tests on every PR
  build-gtfs.yml                scheduled fetch → transform → build → MobilityData gtfs-validator → release
```

## License

MIT — see `LICENSE`. Transmetro's own data remains under whatever license
its publisher applies.
