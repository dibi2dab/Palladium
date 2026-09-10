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
    "GDP": "Gross Domestic Product",
    "DGS10": "10-Year Treasury Rate",
    "DGS2": "2-Year Treasury Rate",
    "DCOILWTICO": "WTI Crude Oil Price",
    "GOLDAMGBD228NLBM": "Gold Price",
    "DTWEXBGS": "Trade Weighted US Dollar Index",
    "INDPRO": "Industrial Production",
    "RSAFS": "Retail Sales",
    "UMCSENT": "Consumer Sentiment",
}


class EconomyCollector(BaseCollector):
    source_name = "economy"

    def collect(self) -> list[Opportunity]:
        items: list[Opportunity] = []
        if FRED_API_KEY:
            items.extend(self._collect_fred())
        else:
            items.extend(self._collect_fred_rss())
        return items

    def _collect_fred(self) -> list[Opportunity]:
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
                date_str = latest.get("date", "")

                if val == "." or prev_val == ".":
                    continue

                try:
                    current = float(val)
                    previous = float(prev_val)
                except (ValueError, TypeError):
                    continue

                change_pct = ((current - previous) / abs(previous) * 100) if previous != 0 else 0

                opp = Opportunity(
                    name=f"{name}: {current}",
                    url=f"https://fred.stlouisfed.org/series/{series_id}",
                    description=f"{name} latest value: {current} (previous: {previous}, change: {change_pct:.2f}%)",
                    category="Economy",
                    source="fred",
                    official_url=f"https://fred.stlouisfed.org/series/{series_id}",
                    metrics=Metrics(),
                    tags=["economy", "macro", series_id.lower()],
                    source_ids=[f"fred:{series_id}"],
                )
                results.append(opp)

            except Exception as e:
                logger.debug(f"FRED {series_id} failed: {e}")

        return results

    def _collect_fred_rss(self) -> list[Opportunity]:
        results: list[Opportunity] = []
        rss_urls = [
            "https://fred.stlouisfed.org/rss/all.xml",
        ]

        for rss_url in rss_urls:
            try:
                resp = requests.get(rss_url, timeout=15, headers={
                    "User-Agent": "Mozilla/5.0 (compatible; OpportunityScanner/1.0)",
                })
                if resp.status_code != 200:
                    continue

                root = ElementTree.fromstring(resp.content)
                ns = {"atom": "http://www.w3.org/2005/Atom"}

                entries = root.findall(".//atom:entry", ns)
                if not entries:
                    entries = root.findall(".//item")

                for entry in entries[:10]:
                    title_el = entry.find("atom:title", ns) or entry.find("title")
                    link_el = entry.find("atom:link", ns) or entry.find("link")
                    if title_el is None:
                        continue

                    title = title_el.text or ""
                    link = ""
                    if link_el is not None:
                        link = link_el.get("href", "") or link_el.text or ""

                    opp = Opportunity(
                        name=title,
                        url=link or rss_url,
                        description=f"Economic indicator update: {title}",
                        category="Economy",
                        source="fred_rss",
                        official_url=link,
                        metrics=Metrics(),
                        tags=["economy", "macro"],
                        source_ids=[f"fredrss:{title[:30]}"],
                    )
                    results.append(opp)

            except Exception as e:
                logger.warning(f"FRED RSS collection failed: {e}")

        return results
