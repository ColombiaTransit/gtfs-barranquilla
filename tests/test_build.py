"""Structural test: given minimal, already-correct GTFS tables, does the
build stage zip them into a feed with the expected files? This
deliberately does NOT exercise fetch/transform (those need real network
sources / real site markup) -- it exists to catch regressions in build.py
in isolation.

Full GTFS spec validation runs in CI via the official MobilityData
gtfs-validator (see .github/workflows/build-gtfs.yml), not here -- this
test only checks that build.py assembles a well-formed zip, not that its
contents satisfy every GTFS rule.
"""
from __future__ import annotations

import zipfile

import pandas as pd
import pytest

from gtfs_pipeline.build import build_feed


@pytest.fixture
def minimal_interim_dir(tmp_path):
    interim = tmp_path / "interim"
    interim.mkdir()

    pd.DataFrame(
        [{"agency_id": "transmetro", "agency_name": "Transmetro S.A.",
          "agency_url": "https://www.transmetro.gov.co",
          "agency_timezone": "America/Bogota", "agency_lang": "es"}]
    ).to_csv(interim / "agency.csv", index=False)

    pd.DataFrame(
        [{"stop_id": "stop_1", "stop_name": "Portal Soledad", "stop_lat": 10.917, "stop_lon": -74.783, "location_type": 1},
         {"stop_id": "stop_2", "stop_name": "Joe Arroyo", "stop_lat": 10.963, "stop_lon": -74.796, "location_type": 1}]
    ).to_csv(interim / "stops.csv", index=False)

    pd.DataFrame(
        [{"route_id": "route_r1", "route_short_name": "R1", "route_long_name": "Soledad - Joe Arroyo", "route_type": 3}]
    ).to_csv(interim / "routes.csv", index=False)

    pd.DataFrame(
        [{"route_id": "route_r1", "service_id": "everyday", "trip_id": "route_r1_trip_0", "direction_id": 0}]
    ).to_csv(interim / "trips.csv", index=False)

    pd.DataFrame(
        [{"trip_id": "route_r1_trip_0", "arrival_time": "05:00:00", "departure_time": "05:00:00", "stop_id": "stop_1", "stop_sequence": 0},
         {"trip_id": "route_r1_trip_0", "arrival_time": "05:20:00", "departure_time": "05:20:00", "stop_id": "stop_2", "stop_sequence": 1}]
    ).to_csv(interim / "stop_times.csv", index=False)

    pd.DataFrame(
        [{"service_id": "everyday", "monday": 1, "tuesday": 1, "wednesday": 1, "thursday": 1,
          "friday": 1, "saturday": 1, "sunday": 1, "start_date": "20260101", "end_date": "20261231"}]
    ).to_csv(interim / "calendar.csv", index=False)

    pd.DataFrame(
        [{"feed_publisher_name": "ColombiaTransit",
          "feed_publisher_url": "https://github.com/ColombiaTransit/gtfs-barranquilla",
          "feed_lang": "es", "default_lang": "es"}]
    ).to_csv(interim / "feed_info.csv", index=False)

    return interim


def test_build_feed_produces_zip(minimal_interim_dir, tmp_path):
    out_dir = tmp_path / "gtfs"
    zip_path = build_feed(interim_dir=minimal_interim_dir, out_dir=out_dir, feed_name="test.zip")
    assert zip_path.exists()


def test_build_feed_contains_required_gtfs_files(minimal_interim_dir, tmp_path):
    out_dir = tmp_path / "gtfs"
    zip_path = build_feed(interim_dir=minimal_interim_dir, out_dir=out_dir, feed_name="test.zip")

    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())

    required = {
        "agency.txt", "stops.txt", "routes.txt", "trips.txt",
        "stop_times.txt", "calendar.txt", "feed_info.txt",
    }
    assert required.issubset(names)
