from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup

from src.collectors.base import BaseCollector
from src.models import Opportunity, Metrics


logger = logging.getLogger(__name__)

SEC_EDGAR_API = "https://efts.sec.gov/LATEST"
SEC_SEARCH = "https://efts.sec.gov/LATEST/search-index"


class MarketCollector(BaseCollector):
    source_name = "markets"

    def collect(self) -> list[Opportunity]:
        items: list[Opportunity] = []
        items.extend(self._collect_sec_filings())
        items.extend(self._collect_stock_news())
        return items

    def _collect_sec_filings(self) -> list[Opportunity]:
        results: list[Opportunity] = []
        try:
            url = f"{SEC_EDGAR_API}/search-index?q=%22material+agreement%22+OR+%22acquisition%22+OR+%22merger%22&dateRange=custom&startdt={(datetime.utcnow() - timedelta(days=7)).strftime('%Y-%m-%d')}&enddt={datetime.utcnow().strftime('%Y-%m-%d')}&forms=8-K,10-K,SC+13D"
            resp = requests.get(url, timeout=20, headers={
                "User-Agent": "OpportunityScanner/1.0 (jjuwoo1117@gmail.com)",
                "Accept": "application/json",
            })
            if resp.status_code == 200:
                data = resp.json()
                hits = data.get("hits", {}).get("hits", [])
                for hit in hits[:20]:
                    source = hit.get("_source", {})
                    company = source.get("display_names", ["Unknown"])[0] if source.get("display_names") else "Unknown"
                    form_type = source.get("form_type", "Unknown")
                    filing_url = f"https://www.sec.gov/Archives/edgar/data/{source.get('entity_id', '')}/{hit.get('_id', '')}"
                    opp = Opportunity(
                        name=company,
                        url=filing_url,
                        description=f"SEC Filing: {form_type} - {company}",
                        category="Public Company",
                        source="sec_edgar",
                        official_url=filing_url,
                        metrics=Metrics(),
                        tags=["sec", "filing", form_type.lower()],
                        source_ids=[f"sec:{hit.get('_id', '')}"],
                    )
                    opp.metrics.news_mentions = 1
                    results.append(opp)
        except Exception as e:
            logger.warning(f"SEC EDGAR collection failed: {e}")

        return results

    def _collect_stock_news(self) -> list[Opportunity]:
        results: list[Opportunity] = []
        feeds = [
            "https://finance.yahoo.com/news/rssindex",
            "https://feeds.bloomberg.com/markets/news.rss",
        ]

        for feed_url in feeds:
            try:
                resp = requests.get(feed_url, timeout=15, headers={
                    "User-Agent": "Mozilla/5.0 (compatible; OpportunityScanner/1.0)",
                })
                if resp.status_code != 200:
                    continue

                soup = BeautifulSoup(resp.text, "xml")
                items = soup.find_all("item")

                for item in items[:15]:
                    title = item.find("title")
                    link = item.find("link")
                    desc = item.find("description")
                    if not title:
                        continue

                    title_text = title.get_text(strip=True)
                    link_text = link.get_text(strip=True) if link else ""
                    desc_text = desc.get_text(strip=True) if desc else title_text

                    opp = Opportunity(
                        name=title_text,
                        url=link_text or feed_url,
                        description=desc_text[:500],
                        category="Market Event",
                        source="market_news",
                        official_url=link_text,
                        metrics=Metrics(news_mentions=1),
                        tags=["market", "news"],
                        source_ids=[f"news:{title_text[:50]}"],
                    )
                    results.append(opp)

            except Exception as e:
                logger.warning(f"Market news collection failed for {feed_url}: {e}")

        return results
