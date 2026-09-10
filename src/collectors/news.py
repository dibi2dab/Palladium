from __future__ import annotations

import logging
import re
from xml.etree import ElementTree

import requests
from bs4 import BeautifulSoup

from src.collectors.base import BaseCollector
from src.models import Opportunity, Metrics


logger = logging.getLogger(__name__)

RSS_FEEDS = [
    ("https://techcrunch.com/feed/", "TechCrunch"),
    ("https://www.crunchbase.com/feed", "Crunchbase"),
    ("https://feeds.arstechnica.com/arstechnica/technology-lab", "Ars Technica"),
    ("https://www.theverge.com/rss/index.xml", "The Verge"),
    ("https://news.ycombinator.com/rss", "Hacker News"),
]

NEWS_KEYWORDS = [
    "funding", "raises", "raised", "series a", "series b", "series c",
    "acquisition", "acquires", "acquired", "ipo", "public",
    "launch", "launches", "launched", "partnership",
    "hire", "hires", "hiring", "ceo", "cto",
    "unicorn", "startup", "valuation",
]


class NewsCollector(BaseCollector):
    source_name = "news"

    def collect(self) -> list[Opportunity]:
        items: list[Opportunity] = []
        for feed_url, source_name in RSS_FEEDS:
            feed_items = self._collect_rss(feed_url, source_name)
            items.extend(feed_items)
        items.extend(self._collect_google_news())
        return items

    def _collect_rss(self, feed_url: str, source_name: str) -> list[Opportunity]:
        results: list[Opportunity] = []
        try:
            resp = requests.get(feed_url, timeout=15, headers={
                "User-Agent": "Mozilla/5.0 (compatible; OpportunityScanner/1.0)",
            })
            if resp.status_code != 200:
                logger.warning(f"RSS {source_name} returned {resp.status_code}")
                return []

            root = ElementTree.fromstring(resp.content)

            ns = {}
            if "atom" in root.tag.lower() or root.tag == "{http://www.w3.org/2005/Atom}feed":
                ns = {"atom": "http://www.w3.org/2005/Atom"}

            items = []
            if ns:
                items = root.findall(".//atom:entry", ns)
            if not items:
                items = root.findall(".//item")

            for item in items[:20]:
                try:
                    opp = self._parse_rss_item(item, source_name, ns)
                    if opp:
                        results.append(opp)
                except Exception:
                    continue

        except Exception as e:
            logger.warning(f"RSS {source_name} failed: {e}")

        return results

    def _parse_rss_item(self, item, source_name: str, ns: dict) -> Opportunity | None:
        if ns:
            title_el = item.find("atom:title", ns)
            link_el = item.find("atom:link", ns)
            desc_el = item.find("atom:summary", ns) or item.find("atom:content", ns)
            pub_el = item.find("atom:published", ns) or item.find("atom:updated", ns)
        else:
            title_el = item.find("title")
            link_el = item.find("link")
            desc_el = item.find("description")
            pub_el = item.find("pubDate")

        if title_el is None:
            return None

        title = (title_el.text or "").strip()
        if not title:
            return None

        link = ""
        if link_el is not None:
            link = link_el.get("href", "") or (link_el.text or "")

        desc = ""
        if desc_el is not None:
            desc = (desc_el.text or "")[:500]

        if not self._is_relevant(title, desc):
            return None

        category = self._guess_category(title, desc)
        pub_date = (pub_el.text or "") if pub_el is not None else ""

        return Opportunity(
            name=title,
            url=link or feed_url_for(source_name),
            description=desc if desc else title,
            category=category,
            source=f"news:{source_name}",
            official_url=link,
            metrics=Metrics(news_mentions=1),
            tags=["news", source_name.lower().replace(" ", "_")],
            source_ids=[f"news:{source_name}:{title[:40]}"],
        )

    def _is_relevant(self, title: str, desc: str) -> bool:
        combined = (title + " " + desc).lower()
        return any(kw in combined for kw in NEWS_KEYWORDS)

    def _guess_category(self, title: str, desc: str) -> str:
        c = (title + " " + desc).lower()
        if any(w in c for w in ["funding", "raises", "raised", "series", "seed"]):
            return "Funding"
        if any(w in c for w in ["acquisition", "acquires", "acquired", "merger"]):
            return "M&A"
        if any(w in c for w in ["ipo", "public", "listing"]):
            return "IPO"
        if any(w in c for w in ["launch", "launches", "product"]):
            return "Product"
        if any(w in c for w in ["hire", "hiring", "ceo", "cto"]):
            return "Hiring"
        if any(w in c for w in ["ai", "llm", "gpt", "robotics"]):
            return "AI/ML"
        if any(w in c for w in ["startup", "unicorn", "valuation"]):
            return "Startup"
        return "News"

    def _collect_google_news(self) -> list[Opportunity]:
        results: list[Opportunity] = []
        queries = [
            "startup funding",
            "technology launch",
            "ai company",
        ]

        for query in queries:
            try:
                url = f"https://news.google.com/rss/search?q={query}+when:1d&hl=en"
                resp = requests.get(url, timeout=15, headers={
                    "User-Agent": "Mozilla/5.0 (compatible; OpportunityScanner/1.0)",
                })
                if resp.status_code != 200:
                    continue

                root = ElementTree.fromstring(resp.content)
                items = root.findall(".//item")

                for item in items[:10]:
                    title_el = item.find("title")
                    link_el = item.find("link")
                    if title_el is None:
                        continue

                    title = (title_el.text or "").strip()
                    link = (link_el.text or "").strip() if link_el is not None else ""

                    if not self._is_relevant(title, ""):
                        continue

                    opp = Opportunity(
                        name=title,
                        url=link or f"https://news.google.com/search?q={query}",
                        description=title,
                        category=self._guess_category(title, ""),
                        source="google_news",
                        official_url=link,
                        metrics=Metrics(news_mentions=1),
                        tags=["news", "google_news"],
                        source_ids=[f"gnews:{title[:40]}"],
                    )
                    results.append(opp)

            except Exception as e:
                logger.debug(f"Google News {query} failed: {e}")

        return results


def feed_url_for(source_name: str) -> str:
    mapping = {
        "TechCrunch": "https://techcrunch.com",
        "Crunchbase": "https://www.crunchbase.com",
        "Ars Technica": "https://arstechnica.com",
        "The Verge": "https://www.theverge.com",
        "Hacker News": "https://news.ycombinator.com",
    }
    return mapping.get(source_name, "")
