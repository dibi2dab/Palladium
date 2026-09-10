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
            q = "%22material+agreement%22+OR+%22acquisition%22+OR+%22merger%22+OR+%22acquisitions+completed%22"
            start = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
            end = datetime.now().strftime("%Y-%m-%d")
            url = f"{SEC_EDGAR_API}/search-index?q={q}&dateRange=custom&startdt={start}&enddt={end}&forms=8-K,10-K,SC+13D&limit=40"
            resp = requests.get(url, timeout=20, headers={
                "User-Agent": "OpportunityScanner/1.0 (jjuwoo1117@gmail.com)",
                "Accept": "application/json",
            })
            if resp.status_code == 200:
                data = resp.json()
                hits = data.get("hits", {}).get("hits", [])
                seen: set = set()
                for hit in hits:
                    source = hit.get("_source", {})
                    company, ticker = _parse_display_name(source.get("display_names"))
                    if not company:
                        continue
                    key = company.lower()
                    if key in seen:
                        continue
                    seen.add(key)

                    form_type = source.get("form", "") or source.get("form_type", "Unknown")
                    filing_date = source.get("file_date", "")
                    desc = source.get("file_description", "") or form_type
                    items = source.get("items", [])

                    filing_url = _build_filing_url(source, hit.get("_id", ""))
                    event = _describe_items(items, source, filing_date)

                    category = _category_for_form(form_type, items)
                    name = f"{company} ({ticker})" if ticker else company
                    results.append(Opportunity(
                        name=name,
                        url=filing_url,
                        description=f"{event} {desc} [{form_type}] {filing_date}".strip(),
                        category=category,
                        source="sec_edgar",
                        official_url=filing_url,
                        metrics=Metrics(news_mentions=1),
                        tags=["sec", "filing", form_type.lower()] + [_item_tag(i) for i in items[:3]],
                        source_ids=[f"sec:{hit.get('_id', '')}"],
                    ))
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


def _parse_display_name(display_names) -> tuple[str, str]:
    """Return (clean_company_name, ticker)."""
    if not display_names:
        return "", ""
    name = display_names[0]
    ticker = ""
    m = re.search(r"\(([A-Z][A-Z0-9\-\.]+(?:,\s*[A-Z][A-Z0-9\-\.]+)*)\)\s*\(CIK", name)
    if m:
        ticker = m.group(1).split(",")[0].strip()
    m2 = re.search(r"^(.*?)\s+\(", name)
    if m2:
        name = m2.group(1).strip()
    return name, ticker


def _build_filing_url(source: dict, doc_id: str) -> str:
    ciks = (source.get("ciks") or [""])[0]
    adsh = source.get("adsh", "")
    if adsh:
        accession = adsh.replace("-", "")
    else:
        accession = doc_id.split(":")[0].replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{int(ciks):013d}/{accession}/{doc_id.split(':')[-1]}"


ITEM_EVENTS = {
    "1.01": "Material agreement entered into",
    "2.01": "Acquisition/asset disposition completed",
    "2.02": "Operating results/financials released",
    "3.02": "Unregistered equity sale",
    "5.02": "Director/officer change",
    "7.01": "Regulation FD disclosure",
    "8.01": "Other material event",
}


def _describe_items(items: list, source: dict, filing_date: str) -> str:
    if not items:
        return source.get("file_description", "") or ""
    parts = []
    for item in items[:3]:
        desc = ITEM_EVENTS.get(item, f"8-K item {item}")
        parts.append(desc)
    return " | ".join(parts)


def _category_for_form(form_type: str, items: list) -> str:
    f = form_type.upper()
    if "SC 13D" in f or "SC 13G" in f:
        return "Activist"
    if f in ("10-K", "10-Q", "20-F"):
        return "Public Company"
    if "2.01" in items or "1.01" in items:
        return "M&A"
    return "Public Company"


def _item_tag(item: str) -> str:
    return " ".join(item.replace(".", "-").split())
