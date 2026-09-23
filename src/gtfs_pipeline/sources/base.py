"""Shared interface + HTTP conventions for all extractors."""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path

import requests

from ..config import SourceSpec

logger = logging.getLogger(__name__)

USER_AGENT = "gtfs-barranquilla-pipeline/0.1 (+https://github.com/ColombiaTransit/gtfs-barranquilla)"

# Every extractor uses this session so we get consistent headers, timeouts,
# and (later, if needed) retry/backoff behavior in one place.
def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    return session


class BaseSource(ABC):
    """One fetch() call: pull raw data for this source and write it to
    spec.output_path. Extractors should be idempotent -- running fetch()
    twice should produce the same file (or clearly fail), so the pipeline
    is safe to re-run in CI.
    """

    def __init__(self, spec: SourceSpec):
        self.spec = spec
        self.session = make_session()

    @abstractmethod
    def fetch(self) -> Path:
        """Fetch raw data and write it under data/raw/. Return the path."""
        raise NotImplementedError

    def _write_bytes(self, content: bytes) -> Path:
        out = self.spec.output_path
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(content)
        logger.info("wrote %s (%d bytes)", out, len(content))
        return out

    def _write_text(self, content: str) -> Path:
        out = self.spec.output_path
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(content, encoding="utf-8")
        logger.info("wrote %s (%d chars)", out, len(content))
        return out
