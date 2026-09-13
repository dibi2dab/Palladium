from __future__ import annotations

import logging
from datetime import date

logger = logging.getLogger(__name__)


SIGNAL_CATEGORIES = {
    "funding": "투자",
    "funding_round": "투자 유치",
    "smart_money": "주요 투자자",
    "accelerator": "액셀러레이터",
    "hiring": "채용",
    "product_launch": "제품 출시",
    "partnership": "파트너십",
    "customer": "고객",
    "community": "커뮤니티",
    "news": "뉴스",
    "github": "GitHub",
    "market_event": "시장 이벤트",
    "macro_event": "거시경제",
    "ma_signal": "M&A",
    "momentum": "성장 모멘텀",
    "funding_withdrawn": "투자 무산/철회",
    "search_interest": "검색 관심도",
    "price_anomaly": "가격 이상(급등/급락)",
    "volume_spike": "거래량 급증",
}


class Signal:
    def __init__(self, entity_id: str, category: str, source: str,
                 description: str = "", strength: int = 1,
                 url: str = "", dedupe_key: str = ""):
        self.entity_id = entity_id
        self.category = category
        self.source = source
        self.description = description
        self.strength = strength
        self.url = url
        self.dedupe_key = dedupe_key
        self.sources: list[str] = [source] if source else []
        self.date = date.today().isoformat()

    def to_dict(self) -> dict:
        return {
            "entity_id": self.entity_id,
            "category": self.category,
            "source": self.source,
            "description": self.description,
            "strength": self.strength,
            "url": self.url,
            "dedupe_key": self.dedupe_key,
            "sources": self.sources,
            "date": self.date,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Signal:
        s = cls(
            entity_id=d["entity_id"],
            category=d["category"],
            source=d.get("source", ""),
            description=d.get("description", ""),
            strength=d.get("strength", 1),
            url=d.get("url", ""),
            dedupe_key=d.get("dedupe_key", ""),
        )
        s.date = d.get("date", s.date)
        s.sources = d.get("sources", [d.get("source", "")] if d.get("source") else [])
        return s


class SignalManager:
    def __init__(self, store):
        self.store = store
        self.signals: list[Signal] = []
        self._load()

    def _load(self):
        raw = self.store.load_signals()
        for s in raw:
            try:
                self.signals.append(Signal.from_dict(s))
            except Exception as e:
                logger.warning(f"Skipping malformed signal: {e}")

    def add(self, signal: Signal):
        self.signals.append(signal)

    def add_for_entity(self, entity_id: str, category: str, source: str,
                       description: str = "", strength: int = 1,
                       url: str = "") -> Signal:
        signal = Signal(entity_id, category, source, description, strength, url)
        self.add(signal)
        return signal

    def add_or_merge(self, entity_id: str, category: str, source: str,
                     description: str = "", strength: int = 1, url: str = "",
                     dedupe_key: str = "") -> Signal:
        """Add a signal, OR merge when the same (entity, category, dedupe_key)
        was already recorded today (a cross-source duplicate).

        Merging increments strength (= source count) and collects sources.
        """
        today = date.today().isoformat()
        if dedupe_key:
            for s in reversed(self.signals):
                if (s.entity_id == entity_id and s.category == category
                        and s.dedupe_key == dedupe_key and s.date == today):
                    s.strength += 1
                    if source and source not in s.sources:
                        s.sources.append(source)
                    if description and not s.description:
                        s.description = description
                    return s
        signal = Signal(entity_id, category, source, description, strength,
                        url, dedupe_key)
        self.add(signal)
        return signal

    def get_recent_signals(self, entity_id: str, days: int = 30) -> list[Signal]:
        from datetime import datetime, timedelta
        cutoff = (datetime.utcnow() - timedelta(days=days)).date().isoformat()
        return [
            s for s in self.signals
            if s.entity_id == entity_id and s.date >= cutoff
        ]

    def get_signals_by_category(self, entity_id: str) -> dict[str, list[Signal]]:
        result: dict[str, list[Signal]] = {}
        for s in self.signals:
            if s.entity_id == entity_id:
                if s.category not in result:
                    result[s.category] = []
                result[s.category].append(s)
        return result

    def count_by_category(self, entity_id: str, days: int = 30) -> dict[str, int]:
        recent = self.get_recent_signals(entity_id, days)
        counts: dict[str, int] = {}
        for s in recent:
            counts[s.category] = counts.get(s.category, 0) + s.strength
        return counts

    def source_count_by_category(self, entity_id: str, days: int = 30) -> dict[str, int]:
        """Distinct source count per category (independent of strength)."""
        recent = self.get_recent_signals(entity_id, days)
        counts: dict[str, int] = {}
        for s in recent:
            if s.category not in counts:
                counts[s.category] = set()
            counts[s.category].update(s.sources or [s.source])
        return {cat: len(v) for cat, v in counts.items()}

    def get_all_categories(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for s in self.signals:
            counts[s.category] = counts.get(s.category, 0) + s.strength
        return counts

    def save(self):
        data = [s.to_dict() for s in self.signals]
        self.store.save_signals(data)

    def cleanup_old(self, days: int = 90):
        from datetime import datetime, timedelta
        cutoff = (datetime.utcnow() - timedelta(days=days)).date().isoformat()
        before = len(self.signals)
        self.signals = [s for s in self.signals if s.date >= cutoff]
        removed = before - len(self.signals)
        if removed > 0:
            logger.info(f"Cleaned up {removed} old signals")