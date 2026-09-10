from __future__ import annotations

import logging
import re
from xml.etree import ElementTree

import requests
from bs4 import BeautifulSoup

from src.collectors.base import BaseCollector
from src.models import Opportunity, Metrics


logger = logging.getLogger(__name__)

PH_FEED = "https://www.producthunt.com/feed"
KS_URL = "https://www.kickstarter.com/discover/advanced"


class ProductCollector(BaseCollector):
    source_name = "products"

    def collect(self) -> list[Opportunity]:
        items: list[Opportunity] = []
        items.extend(self._collect_producthunt())
        items.extend(self._collect_kickstarter())
        return items

    def _collect_producthunt(self) -> list[Opportunity]:
        results: list[Opportunity] = []
        try:
            resp = requests.get(PH_FEED, timeout=20, headers={
                "User-Agent": "Mozilla/5.0 (compatible; OpportunityScanner/1.0)",
            })
            if resp.status_code != 200:
                logger.warning(f"PH feed returned {resp.status_code}")
                return []

            ns = {"atom": "http://www.w3.org/2005/Atom"}
            root = ElementTree.fromstring(resp.content)
            entries = root.findall(".//atom:entry", ns)

            for entry in entries[:30]:
                title_el = entry.find("atom:title", ns)
                link_el = entry.find("atom:link", ns)
                summary_el = entry.find("atom:summary", ns) or entry.find("atom:content", ns)

                if title_el is None:
                    continue

                title = (title_el.text or "").strip()
                if not title:
                    continue

                link = ""
                if link_el is not None:
                    link = link_el.get("href", "")

                summary = ""
                if summary_el is not None:
                    summary = (summary_el.text or "")[:300]
                    summary = BeautifulSoup(summary, "lxml").get_text(strip=True)

                slug = link.rstrip("/").split("/")[-1] if link else ""
                category = self._guess_category(title, summary)

                opp = Opportunity(
                    name=title,
                    url=link or PH_FEED,
                    description=summary or title,
                    category=category,
                    source="producthunt",
                    official_url=link,
                    metrics=Metrics(),
                    tags=["producthunt", "product"],
                    source_ids=[f"ph:{slug}"],
                )
                results.append(opp)

        except Exception as e:
            logger.warning(f"Product Hunt collection failed: {e}")

        return results

    def _guess_category(self, title: str, desc: str) -> str:
        c = (title + " " + desc).lower()
        if any(w in c for w in ["ai", "llm", "gpt", "machine learning", "copilot"]):
            return "AI/ML"
        if any(w in c for w in ["saas", "b2b", "enterprise", "crm"]):
            return "SaaS"
        if any(w in c for w in ["developer", "api", "sdk", "code", "devtool"]):
            return "Developer Tools"
        if any(w in c for w in ["design", "figma", "creative"]):
            return "Design"
        if any(w in c for w in ["productivity", "note", "task"]):
            return "Productivity"
        if any(w in c for w in ["fintech", "payment"]):
            return "Fintech"
        return "Product"

    def _collect_kickstarter(self) -> list[Opportunity]:
        results: list[Opportunity] = []
        try:
            resp = requests.get(KS_URL, timeout=20, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html",
            })
            if resp.status_code != 200:
                return []

            soup = BeautifulSoup(resp.text, "lxml")
            cards = soup.select("[data-project]")
            if not cards:
                cards = soup.select("a[href*='/projects/']")

            for card in cards[:20]:
                try:
                    link = card.select_one("a[href*='/projects/']") if card.name != "a" else card
                    if not link:
                        continue
                    href = link.get("href", "")
                    if "/projects/" not in href:
                        continue

                    name = link.get_text(strip=True)[:100]
                    if not name:
                        name_el = card.select_one("h3, h2")
                        name = name_el.get_text(strip=True) if name_el else "Unknown"

                    url = f"https://www.kickstarter.com{href}" if href.startswith("/") else href

                    opp = Opportunity(
                        name=name,
                        url=url,
                        description=f"Kickstarter: {name}",
                        category="Product",
                        source="kickstarter",
                        official_url=url,
                        metrics=Metrics(),
                        tags=["kickstarter", "product", "crowdfunding"],
                        source_ids=[f"ks:{href.split('/')[-1]}"],
                    )
                    results.append(opp)
                except Exception:
                    continue

        except Exception as e:
            logger.warning(f"Kickstarter collection failed: {e}")

        return results
