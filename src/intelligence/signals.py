from __future__ import annotations

import logging
from datetime import date

logger = logging.getLogger(__name__)


SIGNAL_CATEGORIES = {
    "funding": "Funding",
    "funding_round": "Funding Round",
    "smart_money": "Smart Money",
    "accelerator": "Accelerator",
    "hiring": "Hiring",
    "product_launch": "Product Launch",
    "partnership": "Partnership",
    "customer": "Customer",
    "community": "Community",
    "news": "News",
    "github": "GitHub",
    "market_event": "Market Event",
    "macro_event": "Macro Event",
    "ma_signal": "M&A",
    "momentum": "Growth Momentum",
}


class Signal:
    def __init__(self, entity_id: str, category: str, source: str,
                 description: str = "", strength: int = 1,
                 url: str = ""):
        self.entity_id = entity_id
        self.category = category
        self.source = source
        self.description = description
        self.strength = strength
        self.url = url
        self.date = date.today().isoformat()

    def to_dict(self) -> dict:
        return {
            "entity_id": self.entity_id,
            "category": self.category,
            "source": self.source,
            "description": self.description,
            "strength": self.strength,
            "url": self.url,
            "date": self.date,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Signal:
        s = cls(
            entity_id=d["entity_id"],
            category=d["category"],
            source=d["source"],
            description=d.get("description", ""),
            strength=d.get("strength", 1),
            url=d.get("url", ""),
        )
        s.date = d.get("date", s.date)
        return s


class SignalManager:
    def __init__(self, store):
        self.store = store
        self.signals: list[Signal] = []
        self._load()

    def _load(self):
        raw = self.store.load_signals()
        for s in raw:
            self.signals.append(Signal.from_dict(s))

    def add(self, signal: Signal):
        self.signals.append(signal)

    def add_for_entity(self, entity_id: str, category: str, source: str,
                       description: str = "", strength: int = 1,
                       url: str = "") -> Signal:
        signal = Signal(entity_id, category, source, description, strength, url)
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
