from __future__ import annotations

import logging
import re
from xml.etree import ElementTree

import requests

from src.collectors.base import BaseCollector
from src.collectors.news import RSS_FEEDS
from src.models import Opportunity, Metrics


logger = logging.getLogger(__name__)

FUNDING_FEEDS = [
    ("https://techcrunch.com/category/startups/feed/", "TC Startups"),
    ("https://www.eu-startups.com/feed/", "EU Startups"),
    ("https://tech.eu/feed/", "Tech.eu"),
]

FUNDING_QUERIES = [
    "startup funding round",
    "series a startup raised",
    "seed round venture capital",
    "startup valuation",
]

FUNDING_KEYWORDS = [
    "raised", "funding", "seed round", "series a", "series b", "series c",
    "pre-seed", "backed by", "led by", "investors", "venture capital",
    "accelerator", "y combinator", "techstars", "million", "billion",
]


class FundingCollector(BaseCollector):
    source_name = "funding"

    def collect(self) -> list[Opportunity]:
        items: list[Opportunity] = []
        for feed_url, src in FUNDING_FEEDS:
            try:
                items.extend(self._collect_rss_feed(feed_url, src))
            except Exception as e:
                logger.warning(f"[funding] {src} failed: {e}")
        for query in FUNDING_QUERIES:
            try:
                items.extend(self._collect_google_news(query))
            except Exception as e:
                logger.debug(f"[funding] google news {query} failed: {e}")
        return items

    def _collect_rss_feed(self, feed_url: str, src: str) -> list[Opportunity]:
        results: list[Opportunity] = []
        resp = requests.get(feed_url, timeout=15, headers={
            "User-Agent": "Mozilla/5.0 (compatible; OpportunityScanner/1.0)",
        })
        if resp.status_code != 200:
            logger.warning(f"[funding] {src} returned {resp.status_code}")
            return []

        root = ElementTree.fromstring(resp.content)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        entries = root.findall(".//atom:entry", ns) or root.findall(".//item")

        for entry in entries[:20]:
            title_el = entry.find("atom:title", ns) or entry.find("title")
            link_el = entry.find("atom:link", ns) or entry.find("link")
            desc_el = entry.find("atom:content", ns) or entry.find("description")
            pub_el = entry.find("atom:published", ns) or entry.find("pubDate")

            if title_el is None:
                continue
            title = (title_el.text or "").strip()
            if not title or not self._is_relevant(title):
                continue

            desc = ""
            if desc_el is not None:
                desc = re.sub(r"<[^>]+>", " ", desc_el.text or "")[:500]

            link = ""
            if link_el is not None:
                link = link_el.get("href", "") or (link_el.text or "")

            pub = (pub_el.text or "") if pub_el is not None else ""

            results.append(Opportunity(
                name=title,
                url=link,
                description=desc or title,
                category=self._guess_category(title),
                source=f"funding:{src.lower().replace(' ', '_')}",
                official_url=link,
                metrics=Metrics(news_mentions=1),
                tags=["funding", "startup", src.lower().replace(" ", "_")],
                source_ids=[f"funding:{src}:{title[:40]}"],
            ))
        return results

    def _collect_google_news(self, query: str) -> list[Opportunity]:
        results: list[Opportunity] = []
        url = f"https://news.google.com/rss/search?q={query}+when:2d&hl=en"
        resp = requests.get(url, timeout=15, headers={
            "User-Agent": "Mozilla/5.0 (compatible; OpportunityScanner/1.0)",
        })
        if resp.status_code != 200:
            return []

        root = ElementTree.fromstring(resp.content)
        for item in root.findall(".//item")[:10]:
            title_el = item.find("title")
            link_el = item.find("link")
            if title_el is None:
                continue
            title = (title_el.text or "").strip()
            if not self._is_relevant(title):
                continue
            link = (link_el.text or "").strip() if link_el is not None else ""

            results.append(Opportunity(
                name=title,
                url=link or f"https://news.google.com/search?q={query}",
                description=title,
                category=self._guess_category(title),
                source="funding:google_news",
                official_url=link,
                metrics=Metrics(news_mentions=1),
                tags=["funding", "startup", "google_news"],
                source_ids=[f"funding:gnews:{title[:40]}"],
            ))
        return results

    def _is_relevant(self, title: str) -> bool:
        t = title.lower()
        return any(kw in t for kw in FUNDING_KEYWORDS)

    def _guess_category(self, title: str) -> str:
        t = title.lower()
        if any(w in t for w in ["raised", "funding", "seed", "series", "backed", "venture"]):
            return "Funding"
        if any(w in t for w in ["acquisition", "acquires", "acquired", "merger"]):
            return "M&A"
        if any(w in t for w in ["ipo", "listing"]):
            return "IPO"
        return "Startup"