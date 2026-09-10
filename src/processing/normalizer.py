from __future__ import annotations

import re
from datetime import date
from urllib.parse import urlparse

from src.models import Opportunity


def normalize_opportunity(opp: Opportunity) -> Opportunity:
    opp.name = opp.name.strip()
    opp.description = opp.description.strip()
    opp.url = opp.url.strip()
    opp.category = opp.category.strip() or "Other"
    opp.last_seen = date.today().isoformat()
    return opp


def extract_domain(url: str) -> str:
    try:
        parsed = urlparse(url)
        return parsed.netloc.lower().replace("www.", "")
    except Exception:
        return ""


def normalize_url(url: str) -> str:
    url = url.strip()
    if not url.startswith("http"):
        url = "https://" + url
    parsed = urlparse(url)
    normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/')}"
    if parsed.query:
        normalized += f"?{parsed.query}"
    return normalized


def extract_github_owner_repo(url: str) -> tuple[str, str] | None:
    m = re.search(r"github\.com/([^/]+)/([^/]+)", url)
    if m:
        return m.group(1).lower(), m.group(2).lower().removesuffix(".git")
    return None
