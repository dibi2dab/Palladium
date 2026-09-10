from __future__ import annotations

import logging
from dataclasses import dataclass, field

from src.intelligence.entities import Entity, EntityManager
from src.intelligence.signals import SignalManager

logger = logging.getLogger(__name__)


FUNDING_SIGNALS = [
    ("seed", "Series Seed", 12),
    ("pre-seed", "Pre-Seed", 8),
    ("series_a", "Series A", 15),
    ("series_b", "Series B", 15),
    ("series_c", "Series C", 15),
    ("series_d", "Series D+", 12),
    ("ipo", "IPO", 10),
    ("spac", "SPAC", 8),
    ("acquisition", "Acquisition", 10),
    ("grant", "Grant", 5),
]

MACRO_BOOSTS = {
    "rate_cut": 5,
    "rate_hike": -3,
    "cpi_low": 3,
    "cpi_high": -2,
    "gdp_growth": 3,
    "gdp_decline": -3,
    "employment_strong": 2,
    "employment_weak": -2,
}


@dataclass
class ScoreBreakdown:
    funding: int = 0
    hiring: int = 0
    product: int = 0
    community: int = 0
    news: int = 0
    github: int = 0
    partnership: int = 0
    customer: int = 0
    signal_diversity: int = 0
    cross_source: int = 0
    macro_adjustment: int = 0

    @property
    def total(self) -> int:
        raw = sum([
            self.funding, self.hiring, self.product, self.community,
            self.news, self.github, self.partnership, self.customer,
            self.signal_diversity, self.cross_source, self.macro_adjustment,
        ])
        return max(0, min(100, raw))

    def to_dict(self) -> dict:
        return {
            "funding": self.funding,
            "hiring": self.hiring,
            "product": self.product,
            "community": self.community,
            "news": self.news,
            "github": self.github,
            "partnership": self.partnership,
            "customer": self.customer,
            "signal_diversity": self.signal_diversity,
            "cross_source": self.cross_source,
            "macro_adjustment": self.macro_adjustment,
            "total": self.total,
        }

    def top_signals(self) -> list[tuple[str, int]]:
        items = [
            ("Funding", self.funding),
            ("Hiring", self.hiring),
            ("Product", self.product),
            ("Community", self.community),
            ("News", self.news),
            ("GitHub", self.github),
            ("Partnership", self.partnership),
            ("Customer", self.customer),
        ]
        return [(k, v) for k, v in items if v > 0]


@dataclass
class ScoredEntity:
    entity: Entity
    score: ScoreBreakdown
    confidence: int = 0
    types: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    previous_score: int = 0
    score_change: int = 0


class Scorer:
    def __init__(self, entity_manager: EntityManager, signal_manager: SignalManager,
                 macro_events: list[dict] | None = None):
        self.entities = entity_manager
        self.signals = signal_manager
        self.macro_events = macro_events or []

    def score_all(self) -> list[ScoredEntity]:
        results: list[ScoredEntity] = []
        for entity in self.entities.get_all():
            scored = self._score_entity(entity)
            results.append(scored)
        results.sort(key=lambda s: s.score.total, reverse=True)
        return results

    def _score_entity(self, entity: Entity) -> ScoredEntity:
        breakdown = ScoreBreakdown()
        reasons: list[str] = []

        counts = self.signals.count_by_category(entity.id, days=30)
        all_counts = self.signals.count_by_category(entity.id, days=365)

        breakdown.funding = self._score_funding(counts, reasons)
        breakdown.hiring = self._score_hiring(counts, reasons)
        breakdown.product = self._score_product(counts, reasons)
        breakdown.community = self._score_community(counts, reasons)
        breakdown.news = self._score_news(counts, reasons)
        breakdown.github = self._score_github(counts, entity, reasons)
        breakdown.partnership = self._score_partnership(counts, reasons)
        breakdown.customer = self._score_customer(counts, reasons)
        breakdown.signal_diversity = self._score_diversity(counts, reasons)
        breakdown.cross_source = self._score_cross_source(entity, reasons)
        breakdown.macro_adjustment = self._score_macro(reasons)

        confidence = self._compute_confidence(entity, counts, reasons)
        types = self._determine_types(breakdown, counts, reasons)

        return ScoredEntity(
            entity=entity,
            score=breakdown,
            confidence=confidence,
            types=types,
            reasons=reasons,
        )

    def _score_funding(self, counts: dict, reasons: list) -> int:
        funding = counts.get("funding", 0)
        if funding == 0:
            return 0
        if funding >= 15:
            reasons.append("Major funding round detected")
            return 15
        if funding >= 10:
            reasons.append("Funding event detected")
            return 12
        if funding >= 5:
            reasons.append("Funding activity detected")
            return 8
        reasons.append("Minor funding signal")
        return 4

    def _score_hiring(self, counts: dict, reasons: list) -> int:
        hiring = counts.get("hiring", 0)
        if hiring == 0:
            return 0
        if hiring >= 10:
            reasons.append("Significant hiring activity")
            return 12
        if hiring >= 5:
            reasons.append("Active hiring detected")
            return 8
        reasons.append("Some hiring signals")
        return 4

    def _score_product(self, counts: dict, reasons: list) -> int:
        product = counts.get("product_launch", 0)
        if product == 0:
            return 0
        if product >= 5:
            reasons.append("Multiple product launches/events")
            return 10
        if product >= 2:
            reasons.append("Product launch detected")
            return 8
        reasons.append("Product activity detected")
        return 5

    def _score_community(self, counts: dict, reasons: list) -> int:
        community = counts.get("community", 0)
        if community == 0:
            return 0
        if community >= 8:
            reasons.append("Strong community engagement")
            return 10
        if community >= 3:
            reasons.append("Growing community activity")
            return 6
        reasons.append("Community signals present")
        return 3

    def _score_news(self, counts: dict, reasons: list) -> int:
        news = counts.get("news", 0)
        if news == 0:
            return 0
        if news >= 10:
            reasons.append("High news coverage")
            return 8
        if news >= 5:
            reasons.append("Moderate news coverage")
            return 5
        reasons.append("Some news mentions")
        return 3

    def _score_github(self, counts: dict, entity: Entity, reasons: list) -> int:
        github = counts.get("github", 0)
        if github == 0 and not entity.github:
            return 0
        if github >= 5:
            reasons.append("Strong GitHub activity")
            return 8
        if github >= 2 or entity.github:
            reasons.append("GitHub presence detected")
            return 5
        return 2

    def _score_partnership(self, counts: dict, reasons: list) -> int:
        p = counts.get("partnership", 0)
        if p >= 3:
            reasons.append("Partnership activity detected")
            return 8
        if p >= 1:
            reasons.append("Partnership signal")
            return 4
        return 0

    def _score_customer(self, counts: dict, reasons: list) -> int:
        c = counts.get("customer", 0)
        if c >= 5:
            reasons.append("Customer adoption signals")
            return 10
        if c >= 2:
            reasons.append("Customer traction detected")
            return 6
        if c >= 1:
            reasons.append("Customer signal present")
            return 3
        return 0

    def _score_diversity(self, counts: dict, reasons: list) -> int:
        active = sum(1 for k, v in counts.items() if v > 0 and k != "macro_event")
        if active >= 5:
            reasons.append(f"High signal diversity ({active} categories)")
            return 12
        if active >= 3:
            reasons.append(f"Good signal diversity ({active} categories)")
            return 8
        if active >= 2:
            reasons.append(f"Moderate diversity ({active} categories)")
            return 4
        return 0

    def _score_cross_source(self, entity: Entity, reasons: list) -> int:
        unique_sources = len(set(entity.signal_sources))
        if unique_sources >= 4:
            reasons.append(f"Confirmed across {unique_sources} sources")
            return 10
        if unique_sources >= 3:
            reasons.append(f"Cross-referenced in {unique_sources} sources")
            return 7
        if unique_sources >= 2:
            reasons.append(f"Seen in {unique_sources} sources")
            return 4
        if unique_sources == 1:
            reasons.append("Single source only")
            return 0
        return 0

    def _score_macro(self, reasons: list) -> int:
        adjustment = 0
        for event in self.macro_events:
            etype = event.get("type", "")
            if etype in MACRO_BOOSTS:
                adj = MACRO_BOOSTS[etype]
                adjustment += adj
                if adj > 0:
                    reasons.append(f"Macro tailwind: {etype}")
                elif adj < 0:
                    reasons.append(f"Macro headwind: {etype}")
        return max(-10, min(10, adjustment))

    def _compute_confidence(self, entity: Entity, counts: dict, reasons: list) -> int:
        confidence = 30
        unique_sources = len(set(entity.signal_sources))
        confidence += min(unique_sources * 12, 36)

        total_signals = sum(counts.values())
        confidence += min(total_signals * 2, 20)

        if entity.domain:
            confidence += 5
        if entity.github:
            confidence += 4

        if total_signals < 3:
            confidence -= 15
            reasons.append("Limited data available")

        return max(0, min(100, confidence))

    def _determine_types(self, breakdown: ScoreBreakdown,
                         counts: dict, reasons: list) -> list[str]:
        types = []
        total = breakdown.total

        has_funding = counts.get("funding", 0) > 0
        has_growth = (counts.get("hiring", 0) + counts.get("community", 0) +
                      counts.get("customer", 0)) >= 3

        if total >= 70 and has_funding:
            types.append("INVEST")
        if total >= 60 and has_growth:
            types.append("BUILD")
        if total >= 65 and counts.get("community", 0) >= 3:
            types.append("ACQUIRE")

        if not types:
            types.append("WATCH")

        return types
