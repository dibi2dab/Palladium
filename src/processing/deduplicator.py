from __future__ import annotations

import logging
from urllib.parse import urlparse

from src.models import Opportunity
from src.processing.normalizer import extract_github_owner_repo, extract_domain, normalize_url


logger = logging.getLogger(__name__)


def deduplicate(opportunities: list[Opportunity]) -> list[Opportunity]:
    groups: dict[str, list[Opportunity]] = {}

    for opp in opportunities:
        key = _compute_dedup_key(opp)
        if key not in groups:
            groups[key] = []
        groups[key].append(opp)

    merged: list[Opportunity] = []
    for key, group in groups.items():
        if len(group) == 1:
            merged.append(group[0])
        else:
            merged.append(_merge_group(group))

    logger.info(
        f"Deduplication: {len(opportunities)} items -> {len(merged)} unique "
        f"({len(opportunities) - len(merged)} duplicates removed)"
    )
    return merged


def _compute_dedup_key(opp: Opportunity) -> str:
    github = extract_github_owner_repo(opp.url)
    if github:
        return f"github:{github[0]}/{github[1]}"

    for sid in opp.source_ids:
        if sid.startswith("github:"):
            return sid

    github_gh = _find_github_in_fields(opp)
    if github_gh:
        return f"github:{github_gh[0]}/{github_gh[1]}"

    domain = extract_domain(opp.url)
    if domain and domain not in ("news.ycombinator.com", "www.producthunt.com"):
        return f"domain:{domain}"

    return f"name:{opp.name.lower().strip()}"


def _find_github_in_fields(opp: Opportunity) -> tuple[str, str] | None:
    if opp.official_url:
        gh = extract_github_owner_repo(opp.official_url)
        if gh:
            return gh
    for tag in opp.tags:
        gh = extract_github_owner_repo(tag)
        if gh:
            return gh
    return None


def _merge_group(group: list[Opportunity]) -> Opportunity:
    best = max(group, key=lambda o: len(o.description))
    sources = set()
    source_ids = []
    for opp in group:
        sources.add(opp.source)
        for sid in opp.source_ids:
            if sid not in source_ids:
                source_ids.append(sid)

    best.source = "+".join(sorted(sources))
    best.source_ids = source_ids
    best.tags = list(set(best.tags))

    for opp in group:
        if opp.metrics.github_stars and not best.metrics.github_stars:
            best.metrics.github_stars = opp.metrics.github_stars
        if opp.metrics.github_forks and not best.metrics.github_forks:
            best.metrics.github_forks = opp.metrics.github_forks
        if opp.metrics.producthunt_votes and not best.metrics.producthunt_votes:
            best.metrics.producthunt_votes = opp.metrics.producthunt_votes
        if opp.metrics.hackernews_points and not best.metrics.hackernews_points:
            best.metrics.hackernews_points = opp.metrics.hackernews_points
        if opp.metrics.hackernews_comments and not best.metrics.hackernews_comments:
            best.metrics.hackernews_comments = opp.metrics.hackernews_comments

    return best
