"""Loads config/sources.yml and resolves the standard data directories.

Centralizing paths here means every module agrees on where raw/interim/gtfs
files live, and it's the one place that needs to change if the layout moves.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "config" / "sources.yml"

RAW_DIR = REPO_ROOT / "data" / "raw"
INTERIM_DIR = REPO_ROOT / "data" / "interim"
GTFS_DIR = REPO_ROOT / "data" / "gtfs"


@dataclass(frozen=True)
class SourceSpec:
    """One entry from sources.yml, normalized into a small typed object."""

    name: str
    kind: str
    output_file: str
    raw: dict[str, Any]

    @property
    def output_path(self) -> Path:
        return RAW_DIR / self.output_file


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_sources(path: Path = CONFIG_PATH) -> list[SourceSpec]:
    cfg = load_config(path)
    specs = []
    for name, entry in cfg.get("sources", {}).items():
        specs.append(
            SourceSpec(
                name=name,
                kind=entry["kind"],
                output_file=entry["output_file"],
                raw=entry,
            )
        )
    return specs


def load_static(path: Path = CONFIG_PATH) -> dict[str, Any]:
    return load_config(path).get("static", {})


def ensure_data_dirs() -> None:
    for d in (RAW_DIR, INTERIM_DIR, GTFS_DIR):
        d.mkdir(parents=True, exist_ok=True)
