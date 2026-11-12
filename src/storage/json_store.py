from __future__ import annotations

import gzip
import json
import logging
import os
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

    # History is the largest state file (tens of MB and growing). Keep it
    # gzip-compressed so a single daily commit stays well below GitHub's
    # 100 MB per-file push limit. The compression is transparent to callers.
    HISTORY_FILE = "history.json.gz"
    LEGACY_HISTORY_FILE = "history.json"

    def load_history(self) -> dict:
        path = self.data_dir / self.HISTORY_FILE
        if path.exists():
            try:
                with gzip.open(path, "rt", encoding="utf-8") as f:
                    return json.load(f)
            except (OSError, EOFError, json.JSONDecodeError) as e:
                logger.warning(f"Failed to load {path}: {e}")
                return {}

        # Fallback for repositories that still have the pre-gzip file.
        legacy = self.data_dir / self.LEGACY_HISTORY_FILE
        if legacy.exists():
            return self.load(self.LEGACY_HISTORY_FILE, {})
        return {}

    def save_history(self, history: dict):
        path = self.data_dir / self.HISTORY_FILE
        tmp = path.with_name(path.name + ".tmp")
        with gzip.open(tmp, "wt", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, path)

        # Drop the pre-gzip file so it can never be committed again.
        (self.data_dir / self.LEGACY_HISTORY_FILE).unlink(missing_ok=True)
        logger.debug(f"Saved {path}")

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

    def load_meta(self) -> dict:
        return self.load("meta.json", {})

    def save_meta(self, meta: dict):
        self.save("meta.json", meta)
