"""Extractors: one class per `kind` in config/sources.yml.

To add a new source type (e.g. a JSON API), write a class implementing
BaseSource in this package and register it in KIND_REGISTRY below.
"""
from __future__ import annotations

from ..config import SourceSpec
from .base import BaseSource
from .transmetro import TransmetroRouteSource

KIND_REGISTRY: dict[str, type[BaseSource]] = {
    "transmetro_routes": TransmetroRouteSource,
}


def get_source(spec: SourceSpec) -> BaseSource:
    try:
        cls = KIND_REGISTRY[spec.kind]
    except KeyError as exc:
        raise ValueError(
            f"Unknown source kind {spec.kind!r} for source {spec.name!r}. "
            f"Known kinds: {sorted(KIND_REGISTRY)}"
        ) from exc
    return cls(spec)
