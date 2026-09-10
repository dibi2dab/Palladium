from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta

import requests

from src.collectors.base import BaseCollector
from src.models import Opportunity, Metrics


logger = logging.getLogger(__name__)

HN_API = "https://hacker-news.firebaseio.com/v0"


class HackerNewsCollector(BaseCollector):
    source_name = "hackernews"

    def __init__(self, min_points: int = 50, hours_back: int = 24):
        self.min_points = min_points
        self.hours_back = hours_back

    def collect(self) -> list[Opportunity]:
        cutoff = datetime.utcnow() - timedelta(hours=self.hours_back)
        cutoff_ts = cutoff.timestamp()

        top_ids = self._get_top_stories()

        results: list[Opportunity] = []
        for story_id in top_ids[:100]:
            item = self._get_item(story_id)
            if not item:
                continue

            if item.get("type") != "story":
                continue
            if item.get("score", 0) < self.min_points:
                continue
            if item.get("time", 0) < cutoff_ts:
                continue

            opp = self._item_to_opportunity(item)
            if opp:
                results.append(opp)

        return results

    def _get_top_stories(self) -> list[int]:
        resp = requests.get(f"{HN_API}/topstories.json", timeout=15)
        resp.raise_for_status()
        return resp.json()

    def _get_item(self, item_id: int) -> dict | None:
        try:
            resp = requests.get(f"{HN_API}/item/{item_id}.json", timeout=10)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.debug(f"Failed to fetch HN item {item_id}: {e}")
            return None

    def _item_to_opportunity(self, item: dict) -> Opportunity | None:
        title = item.get("title", "").strip()
        url = item.get("url", "")
        hn_url = f"https://news.ycombinator.com/item?id={item['id']}"

        if not title:
            return None

        score = item.get("score", 0)
        comments = item.get("descendants", 0) or 0

        description = title
        if item.get("text"):
            description = item["text"][:500]

        category = self._guess_category(title, url)

        official_url = url if url else hn_url

        return Opportunity(
            name=title,
            url=hn_url,
            description=description,
            category=category,
            source="hackernews",
            official_url=official_url,
            metrics=Metrics(
                hackernews_points=score,
                hackernews_comments=comments,
            ),
            tags=["hackernews", "frontpage"],
            source_ids=[f"hn:{item['id']}"],
        )

    def _guess_category(self, title: str, url: str) -> str:
        combined = (title + " " + url).lower()
        if any(w in combined for w in ["ai", "llm", "gpt", "claude", "gemini", "model", "neural"]):
            return "AI/ML"
        if any(w in combined for w in ["startup", "yc ", "funding", "raised", "series"]):
            return "Startup"
        if any(w in combined for w in ["security", "hack", "breach", "vulnerability"]):
            return "Security"
        if any(w in combined for w in ["open source", "github", "oss", "foss"]):
            return "Open Source"
        if any(w in combined for w in ["api", "sdk", "framework", "library"]):
            return "Developer Tools"
        if any(w in combined for w in ["fintech", "crypto", "bitcoin", "defi"]):
            return "Fintech"
        if any(w in combined for w in ["e-commerce", "shop", "store", "saas"]):
            return "SaaS/Commerce"
        return "Technology"
