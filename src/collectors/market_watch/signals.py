"""Anomaly detection over real series records (급등·급락·거래량 급증).

A signal is emitted ONLY when real values exist to compare — no missing
points, no extrapolation, no fabricated numbers.

  PRICE_ANOMALY_UP    latest >= threshold % above the previous value
  PRICE_ANOMALY_DOWN  latest <= threshold % below the previous value
  PRICE_ACCELERATION  price move AND the PREVIOUS move also exceeded threshold
                      (>= 3 distinct observations required)
  TRADING_VOLUME_SPIKE  latest volume >= volume_ratio x recent median volume,
                      but ONLY for feeds with a stable volume baseline
                      (>= 8 non-zero prior sessions; median >= 5% of peak).
                      Unreliable/sparse volume history is suppressed silently.

The anomaly label (급등/급락) is applied ONLY for a confirmed PRICE move;
a volume spike is reported separately and never promoted to a price surge.
"""
from __future__ import annotations

import logging
from statistics import median

from src import timeutil


logger = logging.getLogger(__name__)

DEFAULT_THRESHOLD = 1.5       # price move % vs previous observation
DEFAULT_VOLUME_RATIO = 2.5    # volume spike vs recent median volume (excl. latest)

PRICE_ANOMALY_UP = "PRICE_ANOMALY_UP"
PRICE_ANOMALY_DOWN = "PRICE_ANOMALY_DOWN"
PRICE_ACCELERATION_UP = "PRICE_ACCELERATION_UP"
PRICE_ACCELERATION_DOWN = "PRICE_ACCELERATION_DOWN"
TRADING_VOLUME_SPIKE = "TRADING_VOLUME_SPIKE"


def _values(records: list[dict]) -> list[float]:
    return [r["value"] for r in records if r.get("value") is not None]


def detect_anomalies(
    records: list[dict],
    symbol: str,
    name: str,
    threshold: float | None = None,
    volume_ratio: float | None = None,
    observed_at: str | None = None,
) -> list[dict]:
    """Detect real price/volume anomalies in an ordered series.

    Returns signal dicts:
      {type, symbol, name, period, current, prev, change_pct, volume,
       avg_volume, volume_ratio, confidence, evidence, observed_at}
    """
    threshold = threshold if threshold is not None else DEFAULT_THRESHOLD
    volume_ratio = volume_ratio if volume_ratio is not None else DEFAULT_VOLUME_RATIO
    observed_at = observed_at or timeutil.date_kst()

    records = [r for r in records if r.get("value") is not None]
    if len(records) < 2:
        return []

    signals: list[dict] = []
    cur = records[-1]
    prev = records[-2]
    if prev["value"] == 0:
        return []

    change_pct = (cur["value"] - prev["value"]) / abs(prev["value"]) * 100.0
    if abs(change_pct) >= threshold:
        price_type = (PRICE_ANOMALY_UP if change_pct > 0 else PRICE_ANOMALY_DOWN)
        signal = {
            "type": price_type,
            "symbol": symbol,
            "name": name,
            "period": cur["date"],
            "current": cur["value"],
            "prev": prev["value"],
            "change_pct": round(change_pct, 3),
            "confidence": min(95, 55 + round(abs(change_pct) * 8, 1)),
            "evidence": (
                f"{name} 가격 {cur['value']:g} "
                f"({cur['date']}) vs 이전 {prev['value']:g} "
                f"({prev['date']}) — {change_pct:+.2f}%"
            ),
            "observed_at": observed_at,
        }

        # Acceleration: the previous move also breached the same threshold
        # (needs at least 3 distinct observations).
        if len(records) >= 3 and records[-2]["value"] != 0:
            prev2 = records[-3]
            prev_move = ((prev["value"] - prev2["value"]) / abs(prev2["value"]) * 100.0)
            if abs(prev_move) >= threshold:
                signal["type"] = (PRICE_ACCELERATION_UP if change_pct > 0
                                  else PRICE_ACCELERATION_DOWN)
                signal["acceleration_pct"] = round(change_pct - prev_move, 3)
        if signal.get("type", "").startswith("PRICE_ANOMALY"):
            label = "급등" if change_pct > 0 else "급락"
            signal["label"] = label
        elif signal.get("type", "").startswith("PRICE_ACCELERATION"):
            signal["label"] = "급등 가속" if change_pct > 0 else "급락 가속"
        signals.append(signal)

    # Volume spike — only when the feed provides a *reliable* volume series.
    # Some feeds (e.g. Yahoo continuous futures) report erratic history: mostly
    # near-zero rows punctuated by 100x jumps, so any "ratio" would be
    # meaningless. Require >= 8 non-zero prior sessions AND a typical level
    # (median) that is at least 5% of the prior peak — i.e. a stable baseline.
    if cur.get("volume") is not None:
        past = [r["volume"] for r in records[:-1] if r.get("volume") is not None]
        nonzero = [v for v in past if v > 0]
        if len(nonzero) >= 8:
            baseline = median(nonzero)
            if baseline > 0 and baseline >= 0.05 * max(nonzero):
                ratio = cur["volume"] / baseline
                if ratio >= volume_ratio:
                    signals.append({
                        "type": TRADING_VOLUME_SPIKE,
                        "symbol": symbol,
                        "name": name,
                        "period": cur["date"],
                        "current": cur["value"],
                        "volume": cur["volume"],
                        "avg_volume": round(baseline, 0),
                        "volume_ratio": round(ratio, 2),
                        "confidence": min(95, 55 + round(ratio * 8, 1)),
                        "evidence": (
                            f"{name} 거래량 {cur['volume']:,} "
                            f"({cur['date']}) vs 최근 중앙값 {round(baseline):,} — "
                            f"{ratio:.2f}배"
                        ),
                        "observed_at": observed_at,
                    })
    return signals