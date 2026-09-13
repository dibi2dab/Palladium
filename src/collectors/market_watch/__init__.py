"""Price-based market-watch module (가격 기반 공개시장 이상 감지).

Real-observation anomaly detection (급등·급락·거래량 급증). Series values are
actual published numbers — a move is reported ONLY when two real values exist
to compare. Backends:

  yahoo   — keyless daily OHLCV for futures/ETFs/indices (price + volume).
            Volume is included when the feed provides it.
  fred    — FRED series observations (price only, requires FRED_API_KEY).

Nothing is ever fabricated. A per-source failure never kills other sources and
never blocks the rest of the pipeline (safe_collect in base).
"""
from src.collectors.market_watch.collector import MarketWatchCollector

__all__ = ["MarketWatchCollector"]