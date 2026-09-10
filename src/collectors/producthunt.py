from __future__ import annotations

import logging
import re

import requests
from bs4 import BeautifulSoup

from src.collectors.base import BaseCollector
from src.models import Opportunity, Metrics


logger = logging.getLogger(__name__)

PH_URL = "https://www.producthunt.com"


class ProductHuntCollector(BaseCollector):
    source_name = "producthunt"

    def collect(self) -> list[Opportunity]:
        return self._scrape_leaderboard()

    def _scrape_leaderboard(self) -> list[Opportunity]:
        resp = requests.get(
            PH_URL,
            timeout=30,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        results: list[Opportunity] = []

        items = soup.select("[data-test='post-item']")
        if not items:
            items = soup.select("main a[href*='/posts/']")

        if not items:
            items = self._fallback_parse(soup)

        for item in items[:30]:
            try:
                opp = self._parse_item(item)
                if opp:
                    results.append(opp)
            except Exception as e:
                logger.debug(f"Failed to parse PH item: {e}")
                continue

        return results

    def _fallback_parse(self, soup: BeautifulSoup) -> list:
        items = []
        for link in soup.find_all("a", href=re.compile(r"/posts/")):
            parent = link.find_parent(["div", "li", "article"])
            if parent and parent not in items:
                items.append(parent)
        return items

    def _parse_item(self, item) -> Opportunity | None:
        title_el = item.select_one("a[href*='/posts/']")
        if not title_el:
            title_el = item.select_one("[data-test='post-name']")
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
            vote_text = votes_el.get_text(strip=True)
            m = re.search(r"(\d+)", vote_text)
            if m:
                votes = int(m.group(1))

        category = self._guess_category(title, description)

        return Opportunity(
            name=title,
            url=post_url,
            description=description,
            category=category,
            source="producthunt",
            official_url=post_url,
            metrics=Metrics(
                producthunt_votes=votes or None,
            ),
            tags=["producthunt", "featured"],
            source_ids=[f"ph:{href.split('/')[-1]}"],
        )

    def _guess_category(self, title: str, description: str) -> str:
        combined = (title + " " + description).lower()
        if any(w in combined for w in ["ai", "llm", "gpt", "machine learning", "copilot"]):
            return "AI/ML"
        if any(w in combined for w in ["no-code", "no code", "automation", "workflow"]):
            return "No-Code/Automation"
        if any(w in combined for w in ["design", "figma", "ui", "ux", "creative"]):
            return "Design"
        if any(w in combined for w in ["fintech", "payment", "billing", "invoice"]):
            return "Fintech"
        if any(w in combined for w in ["saas", "b2b", "enterprise", "crm"]):
            return "SaaS"
        if any(w in combined for w in ["developer", "api", "sdk", "code"]):
            return "Developer Tools"
        if any(w in combined for w in ["productivity", "note", "task", "calendar"]):
            return "Productivity"
        if any(w in combined for w in ["chat", "messaging", "social", "community"]):
            return "Social/Communication"
        return "Product"
