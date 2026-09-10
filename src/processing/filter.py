from __future__ import annotations

import logging
import re

from src.models import Opportunity


logger = logging.getLogger(__name__)


def filter_candidates(
    opportunities: list[Opportunity],
    min_score: int = 0,
) -> list[Opportunity]:
    filtered = []
    for opp in opportunities:
        if not _passes_basic_filter(opp):
            continue
        if _is_low_quality(opp):
            continue
        filtered.append(opp)

    filtered.sort(key=_pre_ai_sort_key, reverse=True)

    logger.info(f"Filter: {len(opportunities)} -> {len(filtered)} candidates")
    return filtered


def _passes_basic_filter(opp: Opportunity) -> bool:
    if not opp.name or len(opp.name.strip()) < 3:
        return False
    if not opp.url or not opp.url.startswith("http"):
        return False
    if not opp.description or len(opp.description.strip()) < 10:
        return False
    return True


def _is_low_quality(opp: Opportunity) -> bool:
    name_lower = opp.name.lower()
    desc_lower = opp.description.lower()

    spam_signals = [
        r"earn money",
        r"make money fast",
        r"get rich",
        r"free followers",
        r"crypto airdrop",
        r"giveaway",
        r"limited time offer",
        r"click here",
        r"join now",
    ]
    for pattern in spam_signals:
        if re.search(pattern, name_lower) or re.search(pattern, desc_lower):
            return True

    skip_categories = ["test", "homework", "todo"]
    if opp.category.lower() in skip_categories:
        return True

    return False


def _pre_ai_sort_key(opp: Opportunity) -> int:
    score = 0

    if opp.metrics.github_stars:
        if opp.metrics.github_stars > 10000:
            score += 50
        elif opp.metrics.github_stars > 1000:
            score += 30
        elif opp.metrics.github_stars > 100:
            score += 15

    if opp.metrics.hackernews_points:
        if opp.metrics.hackernews_points > 300:
            score += 40
        elif opp.metrics.hackernews_points > 100:
            score += 25
        elif opp.metrics.hackernews_points > 50:
            score += 10

    if opp.metrics.producthunt_votes:
        if opp.metrics.producthunt_votes > 500:
            score += 35
        elif opp.metrics.producthunt_votes > 100:
            score += 20
        elif opp.metrics.producthunt_votes > 30:
            score += 10

    multi_source = opp.source.count("+") > 0
    if multi_source:
        score += 15

    high_value_categories = ["ai/ml", "developer tools", "fintech", "saas"]
    if opp.category.lower() in high_value_categories:
        score += 10

    return score
