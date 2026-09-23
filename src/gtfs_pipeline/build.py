"""Assembles data/interim/*.csv into a standard GTFS zip under data/gtfs/.

This module only zips files that already exist in data/interim/ -- it
doesn't know about routes/stops/etc. themselves. That keeps "what a GTFS
feed is" (this file) separate from "how each table gets built"
(transform/*.py).
"""
from __future__ import annotations

import csv
import logging
import zipfile
from pathlib import Path

import pandas as pd

from .config import GTFS_DIR, INTERIM_DIR, load_static

logger = logging.getLogger(__name__)

# GTFS files in the order they're conventionally listed; agency/feed_info
# are static, the rest come from transform/.
REQUIRED_TABLES = ["stops", "routes", "trips", "stop_times", "calendar"]
OPTIONAL_TABLES = ["shapes", "frequencies", "calendar_dates"]


def build_static_tables(interim_dir: Path = INTERIM_DIR) -> None:
    """Writes agency.txt / feed_info.txt from config/sources.yml `static`."""
    static = load_static()
    interim_dir.mkdir(parents=True, exist_ok=True)

    pd.DataFrame([static["agency"]]).to_csv(interim_dir / "agency.csv", index=False)
    pd.DataFrame([static["feed_info"]]).to_csv(interim_dir / "feed_info.csv", index=False)


def build_feed(interim_dir: Path = INTERIM_DIR, out_dir: Path = GTFS_DIR, feed_name: str = "gtfs.zip") -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / feed_name

    tables = ["agency", *REQUIRED_TABLES, "feed_info"]
    missing = [t for t in tables if not (interim_dir / f"{t}.csv").exists()]
    if missing:
        raise FileNotFoundError(
            f"Missing required interim tables before building the feed: {missing}. "
            f"Run the transform stage first (see cli.py `transform`)."
        )

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for table in tables:
            _write_table_into_zip(zf, interim_dir / f"{table}.csv", f"{table}.txt")
        for table in OPTIONAL_TABLES:
            csv_path = interim_dir / f"{table}.csv"
            if csv_path.exists():
                _write_table_into_zip(zf, csv_path, f"{table}.txt")

    logger.info("built %s", out_path)
    return out_path


def _write_table_into_zip(zf: zipfile.ZipFile, csv_path: Path, arcname: str) -> None:
    # GTFS requires files be plain CSV with a header row; re-writing through
    # csv (rather than zf.write(csv_path) directly) normalizes line endings
    # and quoting so pandas' platform-dependent CSV output can't break a
    # consumer's parser.
    df = pd.read_csv(csv_path)
    data = df.to_csv(index=False, lineterminator="\r\n", quoting=csv.QUOTE_MINIMAL)
    zf.writestr(arcname, data)
