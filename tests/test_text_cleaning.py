"""Tests clean_text_field() against the specific problems a real
MobilityData gtfs-validator run found in this pipeline's actual output:
embedded newlines, control characters, and empty/whitespace-only values.
"""
from __future__ import annotations

from gtfs_pipeline.transform.text_cleaning import clean_text_field


def test_collapses_embedded_newlines_to_a_single_space():
    assert clean_text_field("Portal de\nSoledad") == "Portal de Soledad"
    assert clean_text_field("Line one\r\nLine two") == "Line one Line two"


def test_collapses_repeated_whitespace():
    assert clean_text_field("Portal   de    Soledad") == "Portal de Soledad"


def test_strips_control_characters():
    assert clean_text_field("Portal\x00 de\x0bSoledad") == "Portal de Soledad"


def test_strips_leading_and_trailing_whitespace():
    assert clean_text_field("  Portal de Soledad  \n") == "Portal de Soledad"


def test_empty_and_none_input_returns_empty_string():
    assert clean_text_field(None) == ""
    assert clean_text_field("") == ""
    assert clean_text_field("   \n\t  ") == ""


def test_ordinary_text_is_unchanged():
    assert clean_text_field("Estación Joe Arroyo") == "Estación Joe Arroyo"
