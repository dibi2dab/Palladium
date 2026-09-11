"""Market-entry candidate collector.

Scans Korean media (Google News RSS, hl=ko & gl=KR) for coverage of GLOBAL
products/brands — evidence that a foreign product is entering the Korean
market. Each item is named after the extracted English/Latin brand so the
subject stays non-Korean; presence in Korean media is the market-entry signal.

Only REAL headlines are used: when a headline has no usable Latin brand token
(e.g. Korean-only transcription), the item is skipped rather than guessed.
"""
from __future__ import annotations

import logging
import re
from xml.etree import ElementTree

import requests

from src.collectors.base import BaseCollector
from src.models import Opportunity, Metrics


logger = logging.getLogger(__name__)

HANGUL_RE = re.compile(r"[가-힣]")

# Korean-context queries that surface global products in Korean coverage.
QUERIES = [
    "한국 시장 진출",
    "국내 시장 진출",
    "한국 상륙",
    "한국 공식 출시",
    "국내 출시",
    "한국 출시",
]

BRAND_TOKEN_RE = re.compile(r"[A-Z][A-Za-z0-9&\-']{1,23}")

# Headline noise that must never be mistaken for a product brand.
EXCLUDED_TOKENS = {
    "a", "an", "and", "the", "for", "with", "from", "into", "after", "around",
    "meets", "halal", "via", "plus", "business", "smart", "global", "local",
    "official", "as", "at", "by", "of", "on", "to", "in", "top", "best", "new",
    "ytn", "kbs", "mbc", "sbs", "jtbc", "mbn", "edaily", "herald", "korea",
    "korean", "news", "times", "today", "money", "biz", "media", "group",
    "company", "shows", "launches", "unveils", "releases", "introduces",
    "debuts", "expands", "enters", "opens", "first", "takes", "makes",
    "seoul", "kospi", "kosdaq", "stock", "market",
}


def extract_global_brand(title: str) -> str | None:
    """First usable brand token in a Korean headline, or None.

    Accepts title-case Latin words (ChatGPT, Perplexity, Netflix). Skips
    all-caps abbreviations and short codes (AI, GPT, KBS, YTN) that are more
    likely media/broadcast codes or generic terms than product names.
    """
    for tok in BRAND_TOKEN_RE.findall(title or ""):
        low = tok.lower()
        if low in EXCLUDED_TOKENS or len(tok) < 2:
            continue
        if tok.isupper() and len(tok) <= 4:
            continue
        if not any(c.islower() for c in tok) and len(tok) <= 4:
            continue
        return tok
    return None


def guess_category(title: str) -> str:
    d = (title or "").lower()
    if any(w in d for w in ["ai", "인공지능", "llm", "챗봇", "모델"]):
        return "AI/ML"
    if any(w in d for w in ["출시", "런칭", "서비스", "앱", "게임"]):
        return "Product"
    if any(w in d for w in ["투자", "사무소", "진출", "시장"]):
        return "Business"
    return "Product"


class MarketEntryCollector(BaseCollector):
    source_name = "market_entry"

    def collect(self) -> list[Opportunity]:
        results: list[Opportunity] = []
        seen: set[str] = set()
        for query in QUERIES:
            try:
                for item in self._collect_query(query):
                    brand = item[0]
                    if brand in seen:
                        continue
                    seen.add(brand)
                    results.append(item[1])
            except Exception as e:
                logger.warning(f"[market_entry] query '{query}' failed: {e}")
        return results

    def _collect_query(self, query: str) -> list[tuple[str, Opportunity]]:
        results: list[tuple[str, Opportunity]] = []
        url = f"https://news.google.com/rss/search?q={query}+when:2d&hl=ko&gl=KR"
        resp = requests.get(url, timeout=15, headers={
            "User-Agent": "Mozilla/5.0 (compatible; OpportunityScanner/1.0)",
        })
        if resp.status_code != 200:
            return results

        root = ElementTree.fromstring(resp.content)
        for item in root.findall(".//item")[:10]:
            title_el = item.find("title")
            link_el = item.find("link")
            if title_el is None:
                continue
            title = (title_el.text or "").strip()
            if not HANGUL_RE.search(title):
                continue
            brand = extract_global_brand(title)
            if not brand:
                continue
            link = (link_el.text or "").strip() if link_el is not None else ""
            opp = Opportunity(
                name=brand,
                url=link or f"https://news.google.com/search?q={query}&hl=ko",
                description=title[:300],
                category=guess_category(title),
                source="korea_news:market_entry",
                official_url=link,
                metrics=Metrics(news_mentions=1),
                tags=["global", "market_entry", "korean_coverage"],
                source_ids=[f"korea_news:market_entry:{brand}"],
            )
            results.append((brand, opp))
        return results