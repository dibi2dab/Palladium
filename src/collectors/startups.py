from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup

from src.collectors.base import BaseCollector
from src.models import Opportunity, Metrics
from src.config import HN_MIN_POINTS, HN_HOURS_BACK


logger = logging.getLogger(__name__)

HN_API = "https://hacker-news.firebaseio.com/v0"


class StartupCollector(BaseCollector):
    source_name = "startups"

    def __init__(self):
        self.hn_min = HN_MIN_POINTS
        self.hn_hours = HN_HOURS_BACK

    def collect(self) -> list[Opportunity]:
        items: list[Opportunity] = []
        items.extend(self._collect_hn_startups())
        items.extend(self._collect_yc_latest())
        return items

    def _collect_hn_startups(self) -> list[Opportunity]:
        cutoff = datetime.utcnow() - timedelta(hours=self.hn_hours)
        cutoff_ts = cutoff.timestamp()
        results: list[Opportunity] = []

        try:
            resp = requests.get(f"{HN_API}/topstories.json", timeout=15)
            resp.raise_for_status()
            top_ids = resp.json()
        except Exception as e:
            logger.error(f"Failed to fetch HN top stories: {e}")
            return []

        for story_id in top_ids[:120]:
            item = self._get_item(story_id)
            if not item:
                continue
            if item.get("type") != "story":
                continue
            if item.get("time", 0) < cutoff_ts:
                continue

            title = (item.get("title") or "").lower()
            url = (item.get("url") or "").lower()
            combined = title + " " + url

            is_startup = any(w in combined for w in [
                "startup", "yc ", "y combinator", "seed", "series a",
                "series b", "raised", "funding", "launch", "launched",
                "founded", "accelerator", "incubator", "pivot",
            ])
            if not is_startup and item.get("score", 0) < self.hn_min:
                continue

            opp = self._item_to_opp(item)
            if opp:
                results.append(opp)

        return results

    def _get_item(self, item_id: int) -> dict | None:
        try:
            resp = requests.get(f"{HN_API}/item/{item_id}.json", timeout=10)
            resp.raise_for_status()
            return resp.json()
        except Exception:
            return None

    def _item_to_opp(self, item: dict) -> Opportunity | None:
        title = item.get("title", "").strip()
        url = item.get("url", "")
        hn_url = f"https://news.ycombinator.com/item?id={item['id']}"
        if not title:
            return None

        official_url = url if url else hn_url
        return Opportunity(
            name=title,
            url=hn_url,
            description=title,
            category="Startup",
            source="hackernews",
            official_url=official_url,
            metrics=Metrics(
                hackernews_points=item.get("score", 0),
                hackernews_comments=item.get("descendants", 0) or 0,
            ),
            tags=["startup", "hackernews"],
            source_ids=[f"hn:{item['id']}"],
        )

    def _collect_yc_latest(self) -> list[Opportunity]:
        results: list[Opportunity] = []
        try:
            resp = requests.get(
                "https://www.ycombinator.com/companies",
                timeout=20,
                headers={"User-Agent": "Mozilla/5.0 (compatible; OpportunityScanner/1.0)"},
            )
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            cards = soup.select("a[class*='Company']")
            if not cards:
                cards = soup.select("a[href*='/companies/']")

            for card in cards[:30]:
                try:
                    href = card.get("href", "")
                    if "/companies/" not in href:
                        continue
                    name = card.get_text(strip=True)
                    if not name or len(name) < 2:
                        continue
                    url = f"https://www.ycombinator.com{href}" if href.startswith("/") else href
                    opp = Opportunity(
                        name=name,
                        url=url,
                        description=f"YC company: {name}",
                        category="Startup",
                        source="ycombinator",
                        official_url=url,
                        tags=["yc", "startup"],
                        source_ids=[f"yc:{name.lower()}"],
                    )
                    results.append(opp)
                except Exception:
                    continue

        except Exception as e:
            logger.warning(f"YC collection failed: {e}")

        return results
