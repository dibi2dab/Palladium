from __future__ import annotations

import logging
import re

import requests
from bs4 import BeautifulSoup

from src.collectors.base import BaseCollector
from src.models import Opportunity, Metrics


logger = logging.getLogger(__name__)

PH_URL = "https://www.producthunt.com"
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
            resp = requests.get(
                PH_URL,
                timeout=30,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "text/html,application/xhtml+xml",
                },
            )
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            items = soup.select("[data-test='post-item']")
            if not items:
                items = soup.select("main a[href*='/posts/']")
            if not items:
                items = self._fallback_ph(soup)

            for item in items[:25]:
                try:
                    opp = self._parse_ph_item(item)
                    if opp:
                        results.append(opp)
                except Exception:
                    continue

        except Exception as e:
            logger.warning(f"Product Hunt collection failed: {e}")

        return results

    def _fallback_ph(self, soup: BeautifulSoup) -> list:
        items = []
        for link in soup.find_all("a", href=re.compile(r"/posts/")):
            parent = link.find_parent(["div", "li", "article"])
            if parent and parent not in items:
                items.append(parent)
        return items

    def _parse_ph_item(self, item) -> Opportunity | None:
        title_el = item.select_one("a[href*='/posts/']")
        if not title_el:
            return None

        title = title_el.get_text(strip=True)
        href = title_el.get("href", "")
        post_url = f"{PH_URL}{href}" if href.startswith("/") else href

        tagline_el = item.select_one("[data-test='post-tagline']")
        if not tagline_el:
            tagline_el = item.select_one("p")
        description = tagline_el.get_text(strip=True) if tagline_el else title

        votes_el = item.select_one("[data-test='vote-button']")
        votes = 0
        if votes_el:
            m = re.search(r"(\d+)", votes_el.get_text(strip=True))
            if m:
                votes = int(m.group(1))

        category = self._guess_ph_category(title, description)

        return Opportunity(
            name=title,
            url=post_url,
            description=description,
            category=category,
            source="producthunt",
            official_url=post_url,
            metrics=Metrics(producthunt_votes=votes or None),
            tags=["producthunt", "product"],
            source_ids=[f"ph:{href.split('/')[-1]}"],
        )

    def _guess_ph_category(self, title: str, desc: str) -> str:
        c = (title + " " + desc).lower()
        if any(w in c for w in ["ai", "llm", "gpt", "machine learning"]):
            return "AI/ML"
        if any(w in c for w in ["saas", "b2b", "enterprise"]):
            return "SaaS"
        if any(w in c for w in ["developer", "api", "sdk", "code"]):
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
            resp = requests.get(
                KS_URL,
                timeout=20,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; OpportunityScanner/1.0)",
                    "Accept": "text/html",
                },
            )
            if resp.status_code != 200:
                return []

            soup = BeautifulSoup(resp.text, "lxml")
            cards = soup.select("[data-project]")

            if not cards:
                cards = soup.select("li.js-react-proj-card")
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
                        name_el = card.select_one("h3, h2, [class*='title']")
                        name = name_el.get_text(strip=True) if name_el else "Unknown"

                    url = f"https://www.kickstarter.com{href}" if href.startswith("/") else href

                    pledged_el = card.select_one("[class*='pledged'], [class*='raised']")
                    pledged = pledged_el.get_text(strip=True) if pledged_el else ""

                    opp = Opportunity(
                        name=name,
                        url=url,
                        description=f"Kickstarter project: {name} {('Pledged: ' + pledged) if pledged else ''}",
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
