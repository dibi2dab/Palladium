"""Source configuration + fetchers for the market-watch collector.

Configured through PRICE_WATCH_SOURCES (JSON list of dicts). When the env var
is empty, a built-in default watchlist is used (global commodities and macro
rates) so the feature works out of the box:

  {
    "key":   "pa",
    "name":  "팔라듐 (Palladium)",
    "backend": "yahoo",        # "yahoo" (keyless OHLCV) or "fred" (keyed series)
    "symbol":  "PA=F",         # yahoo symbol OR fred series id
    "url":     "https://finance.yahoo.com/quote/PA=F",
    "threshold": 1.5,          # price move % vs previous observation
    "volume_ratio": 2.5        # volume spike vs recent median (stable feeds only)
  }

fred backend sources are skipped (per-source) when FRED_API_KEY is missing.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

import requests

from src.config import FRED_API_KEY

logger = logging.getLogger(__name__)

FRED_API = "https://api.stlouisfed.org/fred"
YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124 Safari/537.36")

MAX_POINTS = 60

DEFAULT_PRECISION = 2

DEFAULT_SOURCES: list[dict] = [
    {"key": "pa", "name": "팔라듐 (Palladium)", "backend": "yahoo",
     "symbol": "PA=F", "url": "https://finance.yahoo.com/quote/PA=F",
     "threshold": 1.5, "volume_ratio": 2.5},
    {"key": "pl", "name": "백금 (Platinum)", "backend": "yahoo",
     "symbol": "PL=F", "url": "https://finance.yahoo.com/quote/PL=F",
     "threshold": 1.5, "volume_ratio": 2.5},
    {"key": "gc", "name": "금 (Gold)", "backend": "yahoo",
     "symbol": "GC=F", "url": "https://finance.yahoo.com/quote/GC=F",
     "threshold": 1.5, "volume_ratio": 2.5},
    {"key": "si", "name": "은 (Silver)", "backend": "yahoo",
     "symbol": "SI=F", "url": "https://finance.yahoo.com/quote/SI=F",
     "threshold": 2.0, "volume_ratio": 2.5},
    {"key": "cl", "name": "서부텍사스산 원유 (WTI)", "backend": "yahoo",
     "symbol": "CL=F", "url": "https://finance.yahoo.com/quote/CL=F",
     "threshold": 2.0, "volume_ratio": 2.5},
    {"key": "hg", "name": "구리 (Copper)", "backend": "yahoo",
     "symbol": "HG=F", "url": "https://finance.yahoo.com/quote/HG=F",
     "threshold": 2.0, "volume_ratio": 2.5},
    # FRED series (official daily data; requires FRED_API_KEY).
    {"key": "dgs10", "name": "미국 10년물 국채수익률", "backend": "fred",
     "symbol": "DGS10",
     "url": "https://fred.stlouisfed.org/series/DGS10",
     "threshold": 5.0},
    {"key": "dtwexbgs", "name": "미국 달러 인덱스", "backend": "fred",
     "symbol": "DTWEXBGS",
     "url": "https://fred.stlouisfed.org/series/DTWEXBGS",
     "threshold": 0.8},
    {"key": "goldam", "name": "금 런던 고시가", "backend": "fred",
     "symbol": "GOLDAMGBD228NLBM",
     "url": "https://fred.stlouisfed.org/series/GOLDAMGBD228NLBM",
     "threshold": 1.5},
]


def configured_sources() -> list[dict]:
    raw = os.environ.get("PRICE_WATCH_SOURCES", "").strip()
    if not raw:
        return [dict(s) for s in DEFAULT_SOURCES]
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("[market_watch] PRICE_WATCH_SOURCES JSON 오류 — 기본 워치리스트 사용: %s", exc)
        return [dict(s) for s in DEFAULT_SOURCES]
    if not isinstance(parsed, list) or not parsed:
        return [dict(s) for s in DEFAULT_SOURCES]
    return parsed


def _rounded(value) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return round(f, DEFAULT_PRECISION)


def fetch_yahoo(symbol: str, limit: int = MAX_POINTS) -> list[dict]:
    """Daily OHLCV for a Yahoo symbol -> [{date, value, volume}, ...] (oldest first)."""
    url = YAHOO_CHART.format(symbol=symbol.replace("=", "%3D"))
    resp = requests.get(
        url,
        params={"interval": "1d", "range": "3mo"},
        timeout=20,
        headers={"User-Agent": UA, "Accept": "application/json"},
    )
    resp.raise_for_status()
    data = resp.json()
    result = (data.get("chart", {}).get("result") or [])[0]
    timestamps = result.get("timestamp") or []
    quote = ((result.get("indicators", {}).get("quote") or [])[0] or {})
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []

    records: list[dict] = []
    for ts, close, vol in zip(timestamps, closes, volumes):
        close_v = _rounded(close)
        if close_v is None:
            continue
        day = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
        vol_v = int(vol) if isinstance(vol, (int, float)) and vol > 0 else None
        records.append({"date": day, "value": close_v, "volume": vol_v})
    return sorted(records, key=lambda r: r["date"])[-limit:]


def fetch_fred(series_id: str, limit: int = MAX_POINTS) -> list[dict]:
    """FRED observations -> [{date, value}, ...] (oldest first)."""
    if not FRED_API_KEY:
        raise RuntimeError("FRED_API_KEY 미설정")
    resp = requests.get(
        f"{FRED_API}/series/observations",
        params={
            "series_id": series_id,
            "api_key": FRED_API_KEY,
            "file_type": "json",
            "sort_order": "desc",
            "limit": limit,
        },
        timeout=20,
        headers={"User-Agent": "Palladium/1.0"},
    )
    resp.raise_for_status()
    data = resp.json()
    records: list[dict] = []
    for obs in data.get("observations", []):
        value = _rounded(obs.get("value"))
        if value is None:
            continue
        records.append({"date": obs.get("date", ""), "value": value})
    return sorted(records, key=lambda r: r["date"])[-limit:]


def fetch_source(src: dict) -> list[dict]:
    """Fetch normalized records for a source dict, dispatching on backend."""
    backend = str(src.get("backend") or "yahoo").lower()
    if backend == "fred":
        return fetch_fred(str(src.get("symbol") or src.get("key") or ""))
    if backend == "yahoo":
        return fetch_yahoo(str(src.get("symbol") or src.get("key") or ""))
    raise ValueError(f"unknown market_watch backend: {backend}")