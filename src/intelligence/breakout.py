from __future__ import annotations

import logging
from datetime import date

logger = logging.getLogger(__name__)


class BreakoutDetector:
    def __init__(self, store):
        self.store = store
        self.history: dict = {}
        self._load()

    def _load(self):
        self.history = self.store.load_history()

    def update(self, entity_id: str, score: int, confidence: int,
               signal_counts: dict, sources: list[str]):
        today = date.today().isoformat()

        if entity_id not in self.history:
            self.history[entity_id] = {"entries": [], "first_seen": today}

        entries = self.history[entity_id]["entries"]

        existing = [e for e in entries if e.get("date") == today]
        entry = {
            "date": today,
            "score": score,
            "confidence": confidence,
            "signal_counts": signal_counts,
            "sources": sources,
        }

        if existing:
            idx = entries.index(existing[0])
            entries[idx] = entry
        else:
            entries.append(entry)

        entries.sort(key=lambda e: e["date"])

    def detect_breakouts(self, threshold: float = 20.0) -> list[dict]:
        breakouts = []

        for eid, data in self.history.items():
            entries = data.get("entries", [])
            if len(entries) < 2:
                continue

            prev = entries[-2]
            curr = entries[-1]

            prev_score = prev.get("score", 0)
            curr_score = curr.get("score", 0)
            if prev_score == 0:
                continue

            score_change = curr_score - prev_score
            score_change_pct = (score_change / prev_score) * 100

            if score_change_pct < threshold:
                continue

            prev_signals = prev.get("signal_counts", {})
            curr_signals = curr.get("signal_counts", {})
            new_categories = []
            for cat, val in curr_signals.items():
                if val > prev_signals.get(cat, 0):
                    new_categories.append(cat)

            breakouts.append({
                "entity_id": eid,
                "prev_score": prev_score,
                "curr_score": curr_score,
                "score_change": score_change,
                "score_change_pct": round(score_change_pct, 1),
                "new_signal_categories": new_categories,
                "first_seen": data.get("first_seen", "Unknown"),
            })

        breakouts.sort(key=lambda b: b["score_change_pct"], reverse=True)
        return breakouts

    def get_trend(self, entity_id: str, entries_n: int = 7) -> list[dict]:
        entries = self.history.get(entity_id, {}).get("entries", [])
        return entries[-entries_n:]

    def save(self):
        self.store.save_history(self.history)

    def get_watchlist_ids(self) -> list[str]:
        watchlist = []
        for eid, data in self.history.items():
            entries = data.get("entries", [])
            if not entries:
                continue
            latest = entries[-1]
            score = latest.get("score", 0)
            if 30 <= score <= 70:
                watchlist.append(eid)
        return watchlist
