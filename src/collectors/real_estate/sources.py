"""Source registry for real-estate statistics files.

Keyless and loginless only. A source is a plain public CSV/JSON file URL.
Additional sources can be configured without code changes via the
REAL_ESTATE_SOURCES environment variable (a JSON list) — this is plain
configuration, not a secret.

Entry format:
  {"key": "unique-id", "name": "표시 이름", "kind": "csv" | "json",
   "url": "https://...", "encoding": "utf-8"}

Robots/ToS policy: every URL added here MUST be a public official statistics
file. Never add endpoints behind login, CAPTCHA, Cloudflare, or dynamic
tokens — fetching those is prohibited by the project rules.
"""
from __future__ import annotations

import json
import logging
import os

import requests


logger = logging.getLogger(__name__)

DEFAULT_SOURCES: list[dict] = []

USER_AGENT = "Mozilla/5.0 (compatible; OpportunityScanner/1.0)"
TIMEOUT = 25
MAX_BYTES = 2_000_000


def configured_sources() -> list[dict]:
    """DEFAULT_SOURCES merged with REAL_ESTATE_SOURCES (JSON list, optional).

    Currently the default registry is empty because no keyless+loginless
    official statistics FILE/SHEET endpoint has been verified yet:
      - data.go.kr 파일데이터   → 로그인 필요
      - KOSIS CSV 출력          → SSO/JS gating
      - reb.or.kr 통계          → JS 그리드 (직접 파일 없음)
    Fill in a confirmed public URL here or via REAL_ESTATE_SOURCES when ready.
    """
    raw = os.environ.get("REAL_ESTATE_SOURCES", "").strip()
    if not raw:
        return list(DEFAULT_SOURCES)
    try:
        extra = json.loads(raw)
    except ValueError:
        logger.warning("[real_estate] REAL_ESTATE_SOURCES is not valid JSON")
        return list(DEFAULT_SOURCES)
    if not isinstance(extra, list):
        logger.warning("[real_estate] REAL_ESTATE_SOURCES must be a JSON list")
        return list(DEFAULT_SOURCES)
    return list(DEFAULT_SOURCES) + extra


def fetch_source(src: dict) -> bytes:
    """Download a public statistics file. Raises RuntimeError on any failure."""
    url = str(src.get("url", "")).strip()
    if not url:
        raise RuntimeError("source url is empty")
    resp = requests.get(url, timeout=TIMEOUT, headers={"User-Agent": USER_AGENT})
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {url}")
    if len(resp.content) > MAX_BYTES:
        raise RuntimeError("payload exceeds size limit")
    return resp.content