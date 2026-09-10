from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, asdict
from datetime import date
from enum import Enum
from typing import Optional


class OpportunityType(str, Enum):
    INVEST = "INVEST"
    BUILD = "BUILD"
    ACQUIRE = "ACQUIRE"
    WATCH = "WATCH"
    IGNORE = "IGNORE"


class Confidence(str, Enum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


@dataclass
class Metrics:
    github_stars: Optional[int] = None
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
class BusinessInfo:
    pricing: Optional[str] = None
    business_model: Optional[str] = None
    is_paid: Optional[bool] = None
    free_tier: Optional[str] = None
    paid_tier: Optional[str] = None
    funding_raised: Optional[str] = None
    funding_amount: Optional[str] = None
    investors: Optional[str] = None
    founded: Optional[str] = None
    company_size: Optional[str] = None
    competitors: Optional[str] = None

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class Analysis:
    market_size: Optional[str] = None
    growth: Optional[str] = None
    traction: Optional[str] = None
    competition: Optional[str] = None
    monetization: Optional[str] = None
    entry_barrier: Optional[str] = None
    timing: Optional[str] = None
    defensibility: Optional[str] = None
    business_potential: Optional[str] = None
    investment_potential: Optional[str] = None
    reasoning: Optional[str] = None
    facts: list[str] = field(default_factory=list)
    inferences: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = {k: v for k, v in asdict(self).items() if v is not None}
        if not d.get("facts"):
            d.pop("facts", None)
        if not d.get("inferences"):
            d.pop("inferences", None)
        return d


@dataclass
class ScoreBreakdown:
    market_size: int = 0
    growth: int = 0
    traction: int = 0
    monetization: int = 0
    competition: int = 0
    entry_barrier: int = 0
    timing: int = 0
    defensibility: int = 0

    @property
    def total(self) -> int:
        return sum([
            self.market_size, self.growth, self.traction,
            self.monetization, self.competition, self.entry_barrier,
            self.timing, self.defensibility,
        ])

    def to_dict(self) -> dict:
        d = asdict(self)
        d["total"] = self.total
        return d


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
    business_info: BusinessInfo = field(default_factory=BusinessInfo)
    analysis: Optional[Analysis] = None
    score: Optional[ScoreBreakdown] = None
    total_score: int = 0
    types: list[str] = field(default_factory=list)
    confidence: str = Confidence.LOW.value
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
            "business_info": self.business_info.to_dict(),
            "analysis": self.analysis.to_dict() if self.analysis else None,
            "score": self.score.to_dict() if self.score else None,
            "total_score": self.total_score,
            "types": self.types,
            "confidence": self.confidence,
            "tags": self.tags,
            "source_ids": self.source_ids,
        }
