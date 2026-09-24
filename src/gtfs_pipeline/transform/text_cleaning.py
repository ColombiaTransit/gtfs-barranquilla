"""Sanitizes scraped free text before it goes into a GTFS field.

Exists because a real MobilityData gtfs-validator run against this
pipeline's actual output found `new_line_in_value`, `invalid_character`,
and `missing_stop_name` errors, plus outright UNPARSABLE_ROWS in
routes.txt and stops.txt -- all traced to scraped prose (stop names, the
"Recorrido" description) carrying raw newlines and control characters
straight through into GTFS fields. GTFS forbids raw newlines in a field
value at all (CSV quoting technically make the file still parse, but the
spec itself disallows it), and a genuinely empty/whitespace-only name is
worse than an error -- it's silently wrong data.

Used at the transform stage (stops.py, routes.py), not in sources/, so the
raw scraped JSONL keeps the original text unmodified for debugging; only
the GTFS-bound copy gets cleaned.
"""
from __future__ import annotations

import re
import unicodedata

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0e-\x1f\x7f]")
_WHITESPACE_RUN_RE = re.compile(r"\s+")  # unicode-aware: catches \t \n \r \x0b \x0c and stray U+2028/U+2029 too

# Invisible/formatting characters that survive both regexes above -- \s does
# NOT match these (verified directly, not assumed), so a field carrying one
# would previously pass through clean_text_field completely untouched.
# U+FEFF (BOM / zero-width no-break space) is the concrete suspect here:
# it's exactly the kind of artifact Excel/Windows-touched source data
# leaves behind, plausible for Transmetro's own KML export pipeline, and a
# real gtfs-validator run keeps reporting a small, STABLE invalid_character
# count that survived every newline/whitespace fix so far -- consistent
# with a few specific stops carrying a genuinely invisible bad character
# rather than the whitespace/newline issues already fixed.
_INVISIBLE_FORMAT_CHARS_RE = re.compile(
    "[\ufeff\u200b\u200c\u200d\u2060\u00ad]"  # BOM, zero-width space/joiners, word joiner, soft hyphen
)


def clean_text_field(value: str | None) -> str:
    """Collapses all whitespace (including embedded newlines) to single
    spaces, strips control characters and invisible formatting characters,
    and trims the result. Returns "" for None/empty input -- callers that
    require a non-empty value (e.g. stop_name) must check for that
    themselves; this function only cleans, it doesn't decide what's
    acceptable.
    """
    if not value:
        return ""
    value = unicodedata.normalize("NFC", value)
    value = _CONTROL_CHARS_RE.sub("", value)
    value = _INVISIBLE_FORMAT_CHARS_RE.sub("", value)
    value = _WHITESPACE_RUN_RE.sub(" ", value)
    return value.strip()
