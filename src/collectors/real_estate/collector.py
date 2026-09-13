"""RealEstateCollector — keyless, loginless public statistics file collector.

Design rules (project policy):
- No API key, secret, token, login, or dynamic token anywhere.
- Graceful per-source failure: one dead source never kills other sources or
  the rest of the pipeline (safe_collect in base).
- Nothing is invented. A series without a comparable prior value emits no
  signal. Values are recorded exactly as published.
"""
from __future__ import annotations

import logging

from src.collectors.base import BaseCollector
from src.collectors.real_estate.parser import parse_source
from src.collectors.real_estate.signals import detect_changes
from src.collectors.real_estate.sources import configured_sources, fetch_source
from src.models import Metrics, Opportunity


logger = logging.getLogger(__name__)

MAX_ITEMS = 60
MAX_SERIES_POINTS = 6


class RealEstateCollector(BaseCollector):
    source_name = "real_estate"

    def __init__(self):
        self.skipped = False
        # Per-source detail surfaced to reports via main (nested under the
        # collector-level status). {"key": {"name", "status", "items", ...}}
        self.source_status: dict[str, dict] = {}

    def collect(self) -> list[Opportunity]:
        sources = configured_sources()
        if not sources:
            self.skipped = True
            logger.info("[real_estate] 공개 부동산 통계 파일 소스 미설정 — SKIPPED")
            return []

        items: list[Opportunity] = []
        for src in sources:
            items.extend(self._collect_source(src))
            if len(items) >= MAX_ITEMS:
                break
        return items

    def _collect_source(self, src: dict) -> list[Opportunity]:
        key = str(src.get("key") or src.get("url") or "unknown")
        name = str(src.get("name") or key)
        kind = str(src.get("kind") or "csv").lower()
        try:
            content = fetch_source(src)
            records = parse_source(kind, content, str(src.get("encoding") or "utf-8"))
        except Exception as exc:
            logger.warning("[real_estate] source %s failed: %s", key, exc)
            self.source_status[key] = {"name": name, "status": "FAILED", "items": 0}
            return []
        if not records:
            logger.info("[real_estate] source %s returned no parseable rows", key)
            self.source_status[key] = {"name": name, "status": "OK", "items": 0}
            return []

        signals = detect_changes(records)
        items = self._to_opportunities(name, key, str(src.get("url", "")), records, signals)
        self.source_status[key] = {
            "name": name, "status": "OK",
            "items": len(items), "rows": len(records), "signals": len(signals),
        }
        return items

    @staticmethod
    def _to_opportunities(
        source_name: str, source_key: str, source_url: str,
        records: list[dict], signals: list[dict],
    ) -> list[Opportunity]:
        groups: dict[tuple[str, str], list[dict]] = {}
        for r in records:
            key = (str(r.get("item") or "지표"), str(r.get("region") or "전체"))
            groups.setdefault(key, []).append(r)
        signal_map: dict[tuple[str, str], list[dict]] = {}
        for s in signals:
            signal_map.setdefault((s["item"], s["region"]), []).append(s)

        items: list[Opportunity] = []
        for (item, region), rows in sorted(groups.items())[:MAX_ITEMS]:
            rows = sorted(rows, key=lambda r: str(r.get("period")))
            latest = rows[-1]
            series: list[dict] = []
            seen: set[str] = set()
            for r in reversed(rows):
                period = str(r["period"])
                if period in seen:
                    continue
                seen.add(period)
                series.append({"period": period, "value": r["value"]})
                if len(series) >= MAX_SERIES_POINTS:
                    break
            series.reverse()

            grp_signals = signal_map.get((item, region), [])
            name = f"{item} ({region})" if item else region
            description = (
                f"{item or '지표'} {region}: {latest['value']:g} "
                f"(기간 {latest['period']}, 공개 통계 파일 {source_name})"
            )
            opp = Opportunity(
                name=name,
                url=source_url,
                description=description,
                category="Real Estate",
                source="real_estate",
                official_url=source_url,
                metrics=Metrics(),
                tags=["korea", "real_estate", "부동산", region],
                source_ids=[f"re:{source_key}:{region}:{item}:{latest['period']}"],
                real_estate={
                    "indicator": item or "지표",
                    "region": region,
                    "period": str(latest["period"]),
                    "value": latest["value"],
                    "unit": "측정값",
                    "source_key": source_key,
                    "source_name": source_name,
                    "source_url": source_url,
                    "series": series,
                    "signals": grp_signals,
                },
            )
            items.append(opp)
        return items