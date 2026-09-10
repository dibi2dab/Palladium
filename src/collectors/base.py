from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from src.models import Opportunity


logger = logging.getLogger(__name__)


class BaseCollector(ABC):
    """Base class for all data source collectors."""

    source_name: str = "unknown"

    @abstractmethod
    def collect(self) -> list[Opportunity]:
        """Collect opportunities from this source.

        Returns a list of Opportunity objects. On failure, return an empty
        list and log the error — never raise.
        """
        ...

    def safe_collect(self) -> tuple[list[Opportunity], Exception | None]:
        """Wrapper that catches exceptions and returns errors safely."""
        try:
            items = self.collect()
            logger.info(f"[{self.source_name}] Collected {len(items)} items")
            return items, None
        except Exception as e:
            logger.error(f"[{self.source_name}] Collection failed: {e}")
            return [], e
