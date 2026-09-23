"""Shared interface + HTTP conventions for all extractors."""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ..config import SourceSpec

logger = logging.getLogger(__name__)

# A real browser UA, not a self-identifying bot string. The listing pages
# on transmetro.gov.co returned a 404 to this pipeline's original
# "gtfs-barranquilla-pipeline/0.1 (+github...)" UA -- both from this
# sandbox and from a real GitHub Actions run -- while the exact same paths
# loaded fine in an actual browser (see the HTML pasted into the
# conversation this was built from). That's consistent with either basic
# bot-blocking on the UA string, or a security layer that only serves
# these routes to something that looks like a browser; it's NOT consistent
# with the path being wrong, since the paths themselves are correct
# (confirmed against real pasted HTML). If requests STILL 404 after this
# change, the next thing to check is whether the exact same URL 404s in a
# fresh private/incognito browser tab (not one that got there by clicking
# through the site) -- if it does, the site may need a JS-executing
# fetch (e.g. Playwright) rather than plain HTTP requests, which would be
# a bigger change worth discussing before implementing.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
_BROWSER_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "es-CO,es;q=0.9,en;q=0.8",
}


# Every extractor uses this session so we get consistent headers, timeouts,
# and retry/backoff behavior in one place.
def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(_BROWSER_HEADERS)

    # transient network hiccups (and occasional 5xx from a small municipal
    # host) shouldn't kill an entire scheduled CI run over one flaky
    # request -- retry a handful of times with backoff before giving up.
    retry = Retry(
        total=3,
        backoff_factor=1.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
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
