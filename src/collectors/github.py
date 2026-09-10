from __future__ import annotations

import logging
import re

import requests
from bs4 import BeautifulSoup

from src.collectors.base import BaseCollector
from src.models import Opportunity, Metrics


logger = logging.getLogger(__name__)

TRENDING_URL = "https://github.com/trending"
TRENDING_API = "https://api.github.com"


class GitHubTrendingCollector(BaseCollector):
    source_name = "github_trending"

    def collect(self) -> list[Opportunity]:
        opportunities: list[Opportunity] = []
        for lang in ["", "python", "javascript", "typescript"]:
            url = f"{TRENDING_URL}/{lang}" if lang else TRENDING_URL
            items = self._scrape_trending(url, lang or "all")
            opportunities.extend(items)
        return opportunities

    def _scrape_trending(self, url: str, language: str) -> list[Opportunity]:
        resp = requests.get(url, timeout=30, headers={
            "User-Agent": "Mozilla/5.0 (compatible; OpportunityScanner/1.0)",
            "Accept": "text/html",
        })
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        results: list[Opportunity] = []
        articles = soup.select("article.Box-row")

        for article in articles[:25]:
            try:
                opp = self._parse_article(article, language)
                if opp:
                    results.append(opp)
            except Exception as e:
                logger.debug(f"Failed to parse article: {e}")
                continue

        return results

    def _parse_article(self, article, language: str) -> Opportunity | None:
        h2 = article.select_one("h2 a")
        if not h2:
            return None

        href = h2.get("href", "").strip("/")
        parts = href.split("/")
        if len(parts) < 2:
            return None

        owner, repo = parts[0], parts[1]
        repo_url = f"https://github.com/{owner}/{repo}"
        name = f"{owner}/{repo}"

        desc_el = article.select_one("p")
        description = desc_el.get_text(strip=True) if desc_el else "No description"

        stars_el = article.select_one("span.d-inline-block.float-sm-right")
        stars_today = 0
        if stars_el:
            text = stars_el.get_text(strip=True)
            m = re.search(r"([\d,]+)", text)
            if m:
                stars_today = int(m.group(1).replace(",", ""))

        star_els = article.select("a.Link--muted")
        stars = 0
        forks = 0
        if len(star_els) >= 1:
            t = star_els[0].get_text(strip=True).replace(",", "")
            if t.isdigit():
                stars = int(t)
        if len(star_els) >= 2:
            t = star_els[1].get_text(strip=True).replace(",", "")
            if t.isdigit():
                forks = int(t)

        lang_el = article.select_one("span[itemprop='programmingLanguage']")
        lang_text = lang_el.get_text(strip=True) if lang_el else language

        category = self._guess_category(description, lang_text)

        return Opportunity(
            name=name,
            url=repo_url,
            description=description,
            category=category,
            source="github_trending",
            official_url=repo_url,
            metrics=Metrics(
                github_stars=stars or None,
                github_forks=forks or None,
            ),
            tags=[lang_text, "trending"] if lang_text else ["trending"],
            source_ids=[f"github:{owner}/{repo}"],
        )

    def _guess_category(self, description: str, language: str) -> str:
        desc_lower = description.lower()
        if any(w in desc_lower for w in ["ai", "llm", "ml", "neural", "model"]):
            return "AI/ML"
        if any(w in desc_lower for w in ["cli", "terminal", "shell", "devtool"]):
            return "Developer Tools"
        if any(w in desc_lower for w in ["api", "backend", "server", "http"]):
            return "Backend"
        if any(w in desc_lower for w in ["frontend", "ui", "react", "vue", "css"]):
            return "Frontend"
        if any(w in desc_lower for w in ["security", "auth", "crypto"]):
            return "Security"
        if any(w in desc_lower for w in ["database", "sql", "db", "storage"]):
            return "Database"
        if any(w in desc_lower for w in ["automation", "bot", "workflow"]):
            return "Automation"
        if language in ("python", "javascript", "typescript", "rust", "go"):
            return f"Software"
        return "Other"
