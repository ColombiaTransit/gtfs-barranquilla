"""gtfs_pipeline: build a GTFS feed for Transmetro (Barranquilla) from
scraped route pages and their embedded KML data.

Pipeline stages (see cli.py for the commands that run each one):
    1. fetch     -- src/gtfs_pipeline/sources/*      raw sources -> data/raw/
    2. transform -- src/gtfs_pipeline/transform/*     data/raw/ -> data/interim/ (tidy tables)
    3. build     -- src/gtfs_pipeline/build.py         data/interim/ -> data/gtfs/*.zip

GTFS spec validation is NOT part of this package -- it runs as a separate
CI step (.github/workflows/build-gtfs.yml) using the official MobilityData
gtfs-validator (Java) against the built zip, rather than a hand-rolled
Python check.
"""

__version__ = "0.1.0"
