"""Period-over-period change detection over series records.

A signal is emitted ONLY when two real values exist to compare — no missing
points, no extrapolation, no fabricated numbers. Thresholds:

  PRICE        ±0.5%   (가격지수/매매가격 변동)
  JEONSE       ±0.5%
  TRANSACTION  ±5.0%   (거래량·인허가 등 노이즈가 큰 수치)
  DEFAULT      ±1.0%

When three or more periods exist and the CURRENT move again exceeds its own
threshold after the previous move did, the signal type escalates to an
..._ACCELERATION variant.
"""
from __future__ import annotations

import logging

from src import timeutil


logger = logging.getLogger(__name__)

BASE_THRESHOLDS = {
    "PRICE": 0.5,
    "JEONSE": 0.5,
    "TRANSACTION": 5.0,
    "DEFAULT": 1.0,
}

SIGNAL_TYPES = {
    "PRICE": "REAL_ESTATE_PRICE_CHANGE",
    "JEONSE": "REAL_ESTATE_JEONSE_CHANGE",
    "TRANSACTION": "REAL_ESTATE_TRANSACTION_CHANGE",
    "DEFAULT": "REAL_ESTATE_MARKET_CHANGE",
}
ACCELERATION_TYPES = {
    kind: sig.replace("_CHANGE", "_ACCELERATION")
    for kind, sig in SIGNAL_TYPES.items()
}


def _kind_of(item: str) -> str:
    s = (item or "").lower()
    if "전세" in s or "보증금" in s:
        return "JEONSE"
    if any(w in s for w in ("거래량", "매매량", "인허가", "착공", "준공", "분양", "거래건")):
        return "TRANSACTION"
    if any(w in s for w in ("가격", "지수", "매매", "평균")):
        return "PRICE"
    return "DEFAULT"


def _latest_value(rows: list[dict]) -> dict | None:
    for r in reversed(rows):
        if r.get("value") is not None:
            return r
    return None


def detect_changes(records: list[dict], observed_at: str | None = None) -> list[dict]:
    """Compare latest vs previous real value per (item, region).

    Returns signal dicts:
      {type, item, region, period, current, prev, change_pct, unit, kind,
       confidence, evidence, observed_at}
    """
    groups: dict[tuple[str, str], list[dict]] = {}
    for r in records:
        key = (str(r.get("item") or "지표"), str(r.get("region") or "전체"))
        groups.setdefault(key, []).append(r)

    observed_at = observed_at or timeutil.date_kst()
    signals: list[dict] = []
    for (item, region), rows in sorted(groups.items()):
        rows = sorted(rows, key=lambda r: (str(r.get("period")), id(r)))
        deduped: list[dict] = []
        seen: set[str] = set()
        for r in rows:
            key = str(r["period"])
            if key in seen:
                continue
            seen.add(key)
            deduped.append(r)
        if len(deduped) < 2:
            continue
        cur = deduped[-1]
        prev = _latest_value(deduped[:-1])
        if prev is None or prev["value"] == 0:
            continue
        change_pct = (cur["value"] - prev["value"]) / abs(prev["value"]) * 100.0
        kind = _kind_of(item)
        threshold = BASE_THRESHOLDS.get(kind, BASE_THRESHOLDS["DEFAULT"])
        if abs(change_pct) < threshold:
            continue

        signal = {
            "type": SIGNAL_TYPES[kind],
            "item": item or "지표",
            "region": region,
            "period": str(cur["period"]),
            "current": cur["value"],
            "prev": prev["value"],
            "change_pct": round(change_pct, 3),
            "unit": "측정값 (기간 대비 %)",
            "kind": kind,
            "confidence": min(90, 50 + round(abs(change_pct) * 8, 1)),
            "evidence": (
                f"{region} {item or '지표'}: 현재 {cur['value']:g} "
                f"(기간 {cur['period']}) vs 이전 {prev['value']:g} "
                f"(기간 {prev['period']}) — {change_pct:+.2f}%"
            ),
            "observed_at": observed_at,
        }

        # Acceleration: the CURRENT move again exceeds the threshold after the
        # PREVIOUS move also did (needs at least 3 distinct periods).
        if len(deduped) >= 3:
            prev2 = _latest_value(deduped[:-2])
            if prev2 is not None and prev2["value"]:
                prev_move = (prev["value"] - prev2["value"]) / abs(prev2["value"]) * 100.0
                if abs(change_pct - prev_move) >= threshold:
                    signal["type"] = ACCELERATION_TYPES[kind]
                    signal["acceleration_pct"] = round(change_pct - prev_move, 3)
        signals.append(signal)
    return signals