from __future__ import annotations

import logging
import re
import time
from xml.etree import ElementTree

import requests

from src.collectors.base import BaseCollector
from src.models import Opportunity, Metrics


logger = logging.getLogger(__name__)

SUBREDDITS = [
    "startups",
    "SideProject",
    "ArtificialIntelligence",
]

REDDIT_KEYWORDS = [
    "launch", "launched", "release", "raised", "funding", "acquired",
    "acquisition", "ipo", "startup", "product", "growth", "traction",
    "revenue", "mrr", "arr", "milestone", "dataset", "open source",
]

ATOM = {"atom": "http://www.w3.org/2005/Atom"}


class RedditCollector(BaseCollector):
    source_name = "reddit"

    def collect(self) -> list[Opportunity]:
        items: list[Opportunity] = []
        for sub in SUBREDDITS:
            try:
                items.extend(self._collect_subreddit(sub))
            except Exception as e:
                logger.warning(f"[reddit] r/{sub} failed: {e}")
            time.sleep(6)
        return items

    def _collect_subreddit(self, sub: str) -> list[Opportunity]:
        results: list[Opportunity] = []
        url = f"https://www.reddit.com/r/{sub}/top/.rss?t=day"
        resp = requests.get(url, timeout=15, headers={
            "User-Agent": "Mozilla/5.0 (compatible; OpportunityScanner/1.0; +https://github.com/dibi2dab/opportunity-scanner)",
        })
        if resp.status_code != 200:
            if resp.status_code == 429:
                logger.warning(f"[reddit] r/{sub} rate-limited (429), skipping")
            else:
                logger.warning(f"[reddit] r/{sub} returned {resp.status_code}")
            return []

        root = ElementTree.fromstring(resp.content)
        entries = root.findall(".//atom:entry", ATOM) or root.findall(".//item")

        for entry in entries[:25]:
            title_el = entry.find("atom:title", ATOM) or entry.find("title")
            link_el = entry.find("atom:link", ATOM) or entry.find("link")
            content_el = entry.find("atom:content", ATOM) or entry.find("description")
            if title_el is None:
                continue

            title = (title_el.text or "").strip()
            if not title:
                continue
            if not self._is_relevant(title):
                continue

            link = ""
            if link_el is not None:
                link = link_el.get("href", "") or (link_el.text or "")

            content = ""
            if content_el is not None:
                content = _strip_html(content_el.text or "")[:300]

            results.append(Opportunity(
                name=title,
                url=link,
                description=content if content else title,
                category=self._guess_category(title),
                source=f"reddit:{sub}",
                official_url=link,
                metrics=Metrics(news_mentions=1),
                tags=["reddit", sub.lower()],
                source_ids=[f"reddit:{sub}:{title[:40]}"],
            ))
        return results

    def _is_relevant(self, title: str) -> bool:
        c = title.lower()
        return any(kw in c for kw in REDDIT_KEYWORDS)

    def _guess_category(self, title: str) -> str:
        c = title.lower()
        if any(w in c for w in ["funding", "raised", "series", "seed"]):
            return "Funding"
        if any(w in c for w in ["acquisition", "acquired", "merger"]):
            return "M&A"
        if any(w in c for w in ["ipo", "public"]):
            return "IPO"
        if any(w in c for w in ["launch", "launched", "release", "product"]):
            return "Product"
        if any(w in c for w in ["startup", "side project", "entrepreneur"]):
            return "Startup"
        if any(w in c for w in ["ai", "llm", "gpt", "model", "dataset"]):
            return "AI/ML"
        if any(w in c for w in ["growth", "traction", "revenue", "mrr", "arr"]):
            return "Growth"
        return "Tech"


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text).strip()