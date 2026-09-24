"""Sanitizes scraped free text before it goes into a GTFS field.

Exists because a real MobilityData gtfs-validator run against this
pipeline's actual output found `new_line_in_value`, `invalid_character`,
and `missing_stop_name` errors, plus outright UNPARSABLE_ROWS in
routes.txt and stops.txt. Traced to three distinct real causes by reading
the actual report.json rather than guessing each time:
  - `new_line_in_value` / most of UNPARSABLE_ROWS: scraped prose (stop
    names, the "Recorrido" description) carrying raw newlines straight
    through into GTFS fields -- GTFS forbids that outright.
  - `missing_stop_name`: a scraped stop name that was empty/whitespace-only
    after cleaning -- worse than an error, it's silently wrong data, so
    stops.py drops that stop entirely rather than writing a blank name.
  - `invalid_character`: confirmed via report.json's actual sampleNotices
    to be U+FFFD (the Unicode replacement character) already present in
    Transmetro's own source data -- e.g. "Nari\ufffdo" where "Nariño" was
    meant. See _REPLACEMENT_CHAR_RE below for why this is stripped, not
    guessed at.

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
_INVISIBLE_FORMAT_CHARS_RE = re.compile(
    "[\ufeff\u200b\u200c\u200d\u2060\u00ad]"  # BOM, zero-width space/joiners, word joiner, soft hyphen
)

# U+FFFD (the Unicode "replacement character") -- CONFIRMED as the actual
# cause of every invalid_character notice a real gtfs-validator run
# reported, by reading the report.json the person uploaded rather than
# guessing further (an earlier guess, the BOM above, turned out not to be
# it -- kept anyway since it's still valid defensive cleaning, just not
# what was actually happening here). The real values were things like
# "Nari\ufffdo" (should be "Nariño") and "49C \ufffd 235" (should be
# "49C - 235" or similar) -- U+FFFD is what a decoder emits when it hits a
# byte sequence it can't decode, so this is mojibake already baked into
# Transmetro's own source data (present in the parsed KML text itself, not
# introduced by anything in this pipeline). The original character is
# genuinely unrecoverable -- U+FFFD carries no information about what it
# replaced -- so guessing a substitute per-occurrence (ñ here, a dash
# there) would risk inventing wrong data. Stripping it is the honest
# choice: "Nari\ufffdo" becomes "Nario" (misspelled but real, parseable
# data) rather than a guess dressed up as a correction.
_REPLACEMENT_CHAR_RE = re.compile("\ufffd")


def clean_text_field(value: str | None) -> str:
    """Collapses all whitespace (including embedded newlines) to single
    spaces, strips control characters, invisible formatting characters,
    and the Unicode replacement character, and trims the result. Returns
    "" for None/empty input -- callers that require a non-empty value
    (e.g. stop_name) must check for that themselves; this function only
    cleans, it doesn't decide what's acceptable.
    """
    if not value:
        return ""
    value = unicodedata.normalize("NFC", value)
    value = _CONTROL_CHARS_RE.sub("", value)
    value = _INVISIBLE_FORMAT_CHARS_RE.sub("", value)
    value = _REPLACEMENT_CHAR_RE.sub("", value)
    value = _WHITESPACE_RUN_RE.sub(" ", value)
    return value.strip()
