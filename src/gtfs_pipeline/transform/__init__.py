"""Transform stage: data/raw/* (whatever shape each source produced) ->
data/interim/*.csv (GTFS-shaped tidy tables, one file per GTFS entity).

Splitting this from sources/ matters because raw fetches should never need
re-running just because a mapping decision changed -- only the functions
here should need edits during day-to-day GTFS modeling work.

Each module below owns exactly one (or a couple of related) GTFS file(s)
and exposes a `build_<entity>(raw_dir) -> pandas.DataFrame` function. See
build.py for how these are assembled into the final feed.
"""
