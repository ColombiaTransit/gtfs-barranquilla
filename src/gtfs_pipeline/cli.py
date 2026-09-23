"""Command-line entry point: `gtfsbaq fetch|transform|build|all`.

Kept thin on purpose -- each command just calls into sources/, transform/,
or build.py. If you're debugging pipeline logic, put the fix in one of
those modules, not here.

NOTE: there is no `validate` command here. GTFS spec validation runs in
CI (.github/workflows/build-gtfs.yml) via the official MobilityData
gtfs-validator (Java, run through its Docker image) against the built
gtfs.zip -- not as a step in this CLI. See that workflow file for the
exact invocation.
"""
from __future__ import annotations

import datetime as dt
import logging

import click

from .build import build_feed, build_static_tables
from .config import INTERIM_DIR, RAW_DIR, ensure_data_dirs, load_sources
from .sources import get_source
from .transform.calendar import build_calendar
from .transform.calendar_dates import build_calendar_dates
from .transform.routes import build_routes
from .transform.shapes import build_shapes
from .transform.stops import build_stops
from .transform.trips_and_stop_times import build_trips_stop_times_frequencies

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@click.group()
def cli() -> None:
    """Transmetro Barranquilla GTFS pipeline."""
    ensure_data_dirs()


@cli.command()
def fetch() -> None:
    """Stage 1: download every source in config/sources.yml into data/raw/."""
    for spec in load_sources():
        logger.info("fetching %s (%s)", spec.name, spec.kind)
        try:
            get_source(spec).fetch()
        except NotImplementedError as exc:
            logger.warning("skipping %s: %s", spec.name, exc)


@cli.command()
@click.option("--include-suspended", is_flag=True, help="Include routes marked SUSPENDIDA on the site.")
def transform(include_suspended: bool) -> None:
    """Stage 2: data/raw/* -> data/interim/*.csv (GTFS-shaped tables)."""
    build_static_tables()

    route_paths = [RAW_DIR / "troncal_routes.jsonl", RAW_DIR / "alimentadora_routes.jsonl"]
    if not any(p.exists() for p in route_paths):
        raise click.ClickException(
            f"None of {[str(p) for p in route_paths]} found -- run `gtfsbaq fetch` first."
        )

    build_stops(route_paths).to_csv(INTERIM_DIR / "stops.csv", index=False)
    build_routes(route_paths, include_suspended=include_suspended).to_csv(INTERIM_DIR / "routes.csv", index=False)
    build_shapes(route_paths, include_suspended=include_suspended).to_csv(INTERIM_DIR / "shapes.csv", index=False)

    today = dt.datetime.now(tz=dt.UTC).date()
    validity_end = today + dt.timedelta(days=365)
    build_calendar(today, validity_end).to_csv(INTERIM_DIR / "calendar.csv", index=False)
    build_calendar_dates(today, validity_end).to_csv(INTERIM_DIR / "calendar_dates.csv", index=False)

    trips, stop_times, frequencies = build_trips_stop_times_frequencies(
        route_paths, include_suspended=include_suspended
    )
    trips.to_csv(INTERIM_DIR / "trips.csv", index=False)
    stop_times.to_csv(INTERIM_DIR / "stop_times.csv", index=False)
    frequencies.to_csv(INTERIM_DIR / "frequencies.csv", index=False)

    logger.info("transform complete -> %s", INTERIM_DIR)


@cli.command()
@click.option("--name", default="gtfs.zip", help="Output zip filename.")
def build(name: str) -> None:
    """Stage 3: data/interim/*.csv -> data/gtfs/<name>."""
    path = build_feed(feed_name=name)
    click.echo(str(path))


@cli.command(name="all")
@click.pass_context
def run_all(ctx: click.Context) -> None:
    """Run fetch -> transform -> build in sequence. Spec validation is a
    separate CI step (see the module docstring above), not part of this
    command."""
    ctx.invoke(fetch)
    ctx.invoke(transform)
    ctx.invoke(build)


if __name__ == "__main__":
    cli()
