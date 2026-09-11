from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, asdict
from datetime import date
from typing import Optional


@dataclass
class Metrics:
    github_stars: Optional[int] = None
    github_stars_today: Optional[int] = None
    github_forks: Optional[int] = None
    github_contributors: Optional[int] = None
    github_recent_commits: Optional[int] = None
    github_open_issues: Optional[int] = None
    producthunt_votes: Optional[int] = None
    producthunt_comments: Optional[int] = None
    hackernews_points: Optional[int] = None
    hackernews_comments: Optional[int] = None
    reddit_mentions: Optional[int] = None
    news_mentions: Optional[int] = None

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class Opportunity:
    name: str
    url: str
    description: str
    category: str
    source: str
    first_seen: str = field(default_factory=lambda: date.today().isoformat())
    last_seen: str = field(default_factory=lambda: date.today().isoformat())
    official_url: Optional[str] = None
    metrics: Metrics = field(default_factory=Metrics)
    tags: list[str] = field(default_factory=list)
    source_ids: list[str] = field(default_factory=list)

    @property
    def id(self) -> str:
        raw = (self.url or self.name).lower().strip()
        return hashlib.md5(raw.encode()).hexdigest()[:12]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "url": self.url,
            "description": self.description,
            "category": self.category,
            "source": self.source,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "official_url": self.official_url,
            "metrics": self.metrics.to_dict(),
            "tags": self.tags,
            "source_ids": self.source_ids,
        }
