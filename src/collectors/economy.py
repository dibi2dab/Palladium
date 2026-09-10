from __future__ import annotations

import logging
import re
from xml.etree import ElementTree

import requests

from src.collectors.base import BaseCollector
from src.models import Opportunity, Metrics
from src.config import FRED_API_KEY


logger = logging.getLogger(__name__)

FRED_API = "https://api.stlouisfed.org/fred"

KEY_SERIES = {
    "FEDFUNDS": "Federal Funds Rate",
    "CPIAUCSL": "Consumer Price Index",
    "UNRATE": "Unemployment Rate",
    "DGS10": "10-Year Treasury Rate",
    "DGS2": "2-Year Treasury Rate",
    "DCOILWTICO": "WTI Crude Oil Price",
    "GOLDAMGBD228NLBM": "Gold Price",
    "DTWEXBGS": "US Dollar Index",
    "INDPRO": "Industrial Production",
    "RSAFS": "Retail Sales",
    "UMCSENT": "Consumer Sentiment",
}


class EconomyCollector(BaseCollector):
    source_name = "economy"

    def collect(self) -> list[Opportunity]:
        if FRED_API_KEY:
            return self._collect_fred_api()
        return self._collect_economy_news()

    def _collect_fred_api(self) -> list[Opportunity]:
        results: list[Opportunity] = []
        for series_id, name in KEY_SERIES.items():
            try:
                resp = requests.get(
                    f"{FRED_API}/series/observations",
                    params={
                        "series_id": series_id,
                        "api_key": FRED_API_KEY,
                        "file_type": "json",
                        "sort_order": "desc",
                        "limit": 2,
                    },
                    timeout=15,
                )
                if resp.status_code != 200:
                    continue
                data = resp.json()
                observations = data.get("observations", [])
                if len(observations) < 2:
                    continue

                latest = observations[0]
                prev = observations[1]
                val = latest.get("value")
                prev_val = prev.get("value")
                if val == "." or prev_val == ".":
                    continue

                current = float(val)
                previous = float(prev_val)
                change_pct = ((current - previous) / abs(previous) * 100) if previous != 0 else 0

                opp = Opportunity(
                    name=f"{name}: {current}",
                    url=f"https://fred.stlouisfed.org/series/{series_id}",
                    description=f"{name}: {current} (prev: {previous}, {change_pct:+.2f}%)",
                    category="Economy",
                    source="fred",
                    official_url=f"https://fred.stlouisfed.org/series/{series_id}",
                    metrics=Metrics(),
                    tags=["economy", "macro", series_id.lower()],
                    source_ids=[f"fred:{series_id}"],
                )
                results.append(opp)
            except Exception as e:
                logger.debug(f"FRED API {series_id} failed: {e}")

        return results

    def _collect_economy_news(self) -> list[Opportunity]:
        results: list[Opportunity] = []
        queries = [
            "federal reserve interest rate",
            "CPI inflation economy",
            "GDP unemployment economic indicator",
        ]

        for query in queries:
            try:
                url = f"https://news.google.com/rss/search?q={query.replace(' ', '+')}+when:1d&hl=en"
                resp = requests.get(url, timeout=15, headers={
                    "User-Agent": "Mozilla/5.0 (compatible; OpportunityScanner/1.0)",
                })
                if resp.status_code != 200:
                    continue

                root = ElementTree.fromstring(resp.content)
                items = root.findall(".//item")

                for item in items[:5]:
                    title_el = item.find("title")
                    link_el = item.find("link")
                    if title_el is None:
                        continue

                    title = (title_el.text or "").strip()
                    link = (link_el.text or "").strip() if link_el is not None else ""

                    if not title:
                        continue

                    opp = Opportunity(
                        name=title,
                        url=link or f"https://news.google.com/search?q={query}",
                        description=title,
                        category="Economy",
                        source="google_news_economy",
                        official_url=link,
                        metrics=Metrics(news_mentions=1),
                        tags=["economy", "macro", "news"],
                        source_ids=[f"gnews_eco:{title[:40]}"],
                    )
                    results.append(opp)

            except Exception as e:
                logger.debug(f"Economy news {query} failed: {e}")

        return results
