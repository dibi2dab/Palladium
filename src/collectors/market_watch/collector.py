"""MarketWatchCollector — real-observation price/volume anomaly collector.

Design rules (project policy):
- No fabrication: a move is reported only when real values exist to compare.
- Graceful per-source failure: one dead source never kills other sources or
  the rest of the pipeline (safe_collect in base).
- Series values are recorded exactly as published.
"""
from __future__ import annotations

import logging

from src.collectors.base import BaseCollector
from src.collectors.market_watch.signals import detect_anomalies
from src.collectors.market_watch.sources import (
    configured_sources, fetch_source,
)
from src.models import Metrics, Opportunity


logger = logging.getLogger(__name__)

MAX_ITEMS = 40
MAX_SERIES_POINTS = 12


class MarketWatchCollector(BaseCollector):
    source_name = "market_watch"

    def __init__(self):
        self.skipped = False
        # Per-source detail surfaced to reports via main (nested under the
        # collector-level status). {"key": {"name", "status", "items", ...}}
        self.source_status: dict[str, dict] = {}

    def collect(self) -> list[Opportunity]:
        sources = configured_sources()
        if not sources:
            self.skipped = True
            logger.info("[market_watch] 워치리스트 미설정 — SKIPPED")
            return []

        items: list[Opportunity] = []
        for src in sources:
            items.extend(self._collect_source(src))
            if len(items) >= MAX_ITEMS:
                break
        return items

    def _collect_source(self, src: dict) -> list[Opportunity]:
        key = str(src.get("key") or src.get("symbol") or src.get("url") or "unknown")
        name = str(src.get("name") or key)
        backend = str(src.get("backend") or "yahoo")
        try:
            records = fetch_source(src)
        except Exception as exc:
            logger.warning("[market_watch] source %s (%s) failed: %s", key, backend, exc)
            self.source_status[key] = {
                "name": name, "backend": backend, "status": "FAILED", "items": 0,
            }
            return []
        if not records:
            logger.info("[market_watch] source %s returned no parseable rows", key)
            self.source_status[key] = {
                "name": name, "backend": backend, "status": "OK", "items": 0,
            }
            return []

        signals = detect_anomalies(
            records,
            symbol=str(src.get("symbol") or key),
            name=name,
            threshold=src.get("threshold"),
            volume_ratio=src.get("volume_ratio"),
        )
        items = [self._to_opportunity(name, key, src, records, signals)]
        self.source_status[key] = {
            "name": name, "backend": backend, "status": "OK",
            "items": len(items), "points": len(records), "signals": len(signals),
        }
        return items

    @staticmethod
    def _to_opportunity(
        source_name: str, source_key: str, src: dict, records: list[dict],
        signals: list[dict],
    ) -> Opportunity:
        latest = records[-1]
        prev = records[-2] if len(records) >= 2 else None
        symbol = str(src.get("symbol") or source_key)
        series = [
            {k: r[k] for k in ("date", "value", "volume") if r.get(k) is not None}
            for r in records[-MAX_SERIES_POINTS:]
        ]

        if prev and prev["value"]:
            move = (latest["value"] - prev["value"]) / abs(prev["value"]) * 100.0
            move_txt = f" (전일 {prev['value']:g}, {move:+.2f}%)"
        else:
            move_txt = ""

        description = (
            f"{source_name}: {latest['value']:g} ({latest['date']}{move_txt})"
        )
        return Opportunity(
            name=f"{source_name} ({symbol})",
            url=str(src.get("url") or ""),
            description=description,
            category="Market Event",
            source="market_watch",
            official_url=str(src.get("url") or ""),
            metrics=Metrics(),
            tags=["market_watch", "market_event", symbol.lower(), source_key],
            source_ids=[f"mw:{source_key}:{latest['date']}"],
            market_watch={
                "symbol": symbol,
                "name": source_name,
                "period": str(latest["date"]),
                "value": latest["value"],
                "prev": prev["value"] if prev else None,
                "unit": "USD",
                "backend": str(src.get("backend") or "yahoo"),
                "source_key": source_key,
                "source_name": source_name,
                "source_url": str(src.get("url") or ""),
                "series": series,
                "signals": signals,
            },
        )