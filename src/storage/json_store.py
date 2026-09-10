from __future__ import annotations

import json
import logging
from pathlib import Path

from src.config import DATA_DIR


logger = logging.getLogger(__name__)


class JsonStore:
    def __init__(self, data_dir: Path | None = None):
        self.data_dir = data_dir or DATA_DIR
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def load(self, filename: str, default=None):
        path = self.data_dir / filename
        if not path.exists():
            return default if default is not None else {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to load {path}: {e}")
            return default if default is not None else {}

    def save(self, filename: str, data):
        path = self.data_dir / filename
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.debug(f"Saved {path}")

    def load_entities(self) -> dict:
        return self.load("entities.json", {})

    def save_entities(self, entities: dict):
        self.save("entities.json", entities)

    def load_signals(self) -> list:
        return self.load("signals.json", [])

    def save_signals(self, signals: list):
        self.save("signals.json", signals)

    def load_history(self) -> dict:
        return self.load("history.json", {})

    def save_history(self, history: dict):
        self.save("history.json", history)

    def load_watchlist(self) -> list:
        return self.load("watchlist.json", [])

    def save_watchlist(self, watchlist: list):
        self.save("watchlist.json", watchlist)

    def load_scores(self) -> dict:
        return self.load("scores.json", {})

    def save_scores(self, scores: dict):
        self.save("scores.json", scores)

    def load_events(self) -> list:
        return self.load("events.json", [])

    def save_events(self, events: list):
        self.save("events.json", events)
