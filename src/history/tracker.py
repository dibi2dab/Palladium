from __future__ import annotations

import json
import logging
import os
from datetime import date
from pathlib import Path

from src.models import Opportunity


logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent.parent / "data"


class HistoryTracker:
    def __init__(self, data_dir: Path | None = None):
        self.data_dir = data_dir or DATA_DIR
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.history_path = self.data_dir / "history.json"
        self.opportunities_path = self.data_dir / "opportunities.json"
        self.history = self._load_json(self.history_path, {})
        self.opportunities = self._load_json(self.opportunities_path, {})

    def _load_json(self, path: Path, default):
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return default
        return default

    def _save_json(self, path: Path, data):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def save(self):
        self._save_json(self.history_path, self.history)
        self._save_json(self.opportunities_path, self.opportunities)
        logger.info("History data saved")

    def record_opportunity(self, opp: Opportunity):
        opp_id = opp.id
        today = date.today().isoformat()

        entry = self.opportunities.get(opp_id, {})
        entry["id"] = opp_id
        entry["name"] = opp.name
        entry["url"] = opp.url
        entry["category"] = opp.category
        entry["source"] = opp.source
        entry["first_seen"] = entry.get("first_seen", today)
        entry["last_seen"] = today
        entry["latest_score"] = opp.total_score
        entry["latest_types"] = opp.types
        entry["latest_confidence"] = opp.confidence

        if opp.metrics.github_stars:
            entry["latest_github_stars"] = opp.metrics.github_stars
        if opp.metrics.hackernews_points:
            entry["latest_hackernews_points"] = opp.metrics.hackernews_points
        if opp.metrics.producthunt_votes:
            entry["latest_producthunt_votes"] = opp.metrics.producthunt_votes

        self.opportunities[opp_id] = entry

        if opp_id not in self.history:
            self.history[opp_id] = []

        history_entry = {
            "date": today,
            "score": opp.total_score,
            "types": opp.types,
            "confidence": opp.confidence,
        }
        if opp.metrics.github_stars:
            history_entry["github_stars"] = opp.metrics.github_stars
        if opp.metrics.hackernews_points:
            history_entry["hackernews_points"] = opp.metrics.hackernews_points
        if opp.metrics.producthunt_votes:
            history_entry["producthunt_votes"] = opp.metrics.producthunt_votes

        existing_dates = [h.get("date") for h in self.history[opp_id]]
        if today not in existing_dates:
            self.history[opp_id].append(history_entry)
        else:
            for h in self.history[opp_id]:
                if h.get("date") == today:
                    h.update(history_entry)
                    break

    def get_breakouts(self, threshold_percent: float = 50.0) -> list[dict]:
        breakouts = []
        for opp_id, history in self.history.items():
            if len(history) < 2:
                continue

            sorted_history = sorted(history, key=lambda h: h["date"])
            prev = sorted_history[-2]
            curr = sorted_history[-1]

            prev_score = prev.get("score", 0)
            curr_score = curr.get("score", 0)
            if prev_score == 0:
                continue

            score_change = ((curr_score - prev_score) / prev_score) * 100

            stars_change = 0
            prev_stars = prev.get("github_stars", 0) or 0
            curr_stars = curr.get("github_stars", 0) or 0
            if prev_stars > 0:
                stars_change = ((curr_stars - prev_stars) / prev_stars) * 100

            if score_change >= threshold_percent or stars_change >= threshold_percent:
                entry = self.opportunities.get(opp_id, {})
                breakouts.append({
                    "name": entry.get("name", opp_id),
                    "url": entry.get("url", ""),
                    "first_seen": entry.get("first_seen", "Unknown"),
                    "prev_score": prev_score,
                    "curr_score": curr_score,
                    "score_change_percent": round(score_change, 1),
                    "prev_stars": prev_stars,
                    "curr_stars": curr_stars,
                    "stars_change_percent": round(stars_change, 1),
                })

        breakouts.sort(key=lambda b: b["score_change_percent"], reverse=True)
        return breakouts

    def get_watchlist(self) -> list[dict]:
        watchlist = []
        for opp_id, entry in self.opportunities.items():
            types = entry.get("latest_types", [])
            if "WATCH" in types:
                watchlist.append({
                    "name": entry.get("name", opp_id),
                    "url": entry.get("url", ""),
                    "score": entry.get("latest_score", 0),
                    "first_seen": entry.get("first_seen", "Unknown"),
                })
        watchlist.sort(key=lambda w: w["score"], reverse=True)
        return watchlist

    def get_previous(self, opp_id: str) -> dict | None:
        history = self.history.get(opp_id, [])
        if len(history) < 2:
            return None
        sorted_history = sorted(history, key=lambda h: h["date"])
        return sorted_history[-2]
