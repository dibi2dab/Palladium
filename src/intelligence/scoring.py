from __future__ import annotations

import logging
from dataclasses import dataclass, field

from src.intelligence.entities import Entity, EntityManager
from src.intelligence.signals import SignalManager
from src.intelligence.funding import (
    PRE_SEED, SEED, SERIES_A, SERIES_B, SERIES_C, GROWTH,
    UNKNOWN, BIG_TECH, funding_momentum, stage_advanced,
)

logger = logging.getLogger(__name__)


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
    smart_money: int = 0
    accelerator: int = 0
    hiring: int = 0
    product: int = 0
    community: int = 0
    news: int = 0
    github: int = 0
    partnership: int = 0
    customer: int = 0
    momentum: int = 0
    signal_diversity: int = 0
    cross_source: int = 0
    macro_adjustment: int = 0

    @property
    def total(self) -> int:
        raw = sum([
            self.funding, self.smart_money, self.accelerator, self.hiring,
            self.product, self.community, self.news, self.github,
            self.partnership, self.customer, self.momentum,
            self.signal_diversity, self.cross_source, self.macro_adjustment,
        ])
        return max(0, min(100, raw))

    def to_dict(self) -> dict:
        return {
            "funding": self.funding,
            "smart_money": self.smart_money,
            "accelerator": self.accelerator,
            "hiring": self.hiring,
            "product": self.product,
            "community": self.community,
            "news": self.news,
            "github": self.github,
            "partnership": self.partnership,
            "customer": self.customer,
            "momentum": self.momentum,
            "signal_diversity": self.signal_diversity,
            "cross_source": self.cross_source,
            "macro_adjustment": self.macro_adjustment,
            "total": self.total,
        }

    def top_signals(self) -> list[tuple[str, int]]:
        items = [
            ("Funding", self.funding),
            ("Smart Money", self.smart_money),
            ("Accelerator", self.accelerator),
            ("Hiring", self.hiring),
            ("Product", self.product),
            ("Momentum", self.momentum),
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
                 macro_events: list[dict] | None = None,
                 history: dict | None = None):
        self.entities = entity_manager
        self.signals = signal_manager
        self.macro_events = macro_events or []
        self.history = history or {}

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

        breakdown.funding = self._score_funding(counts, entity, reasons)
        breakdown.smart_money = self._score_smart_money(entity, counts, reasons)
        breakdown.accelerator = self._score_accelerator(entity, counts, reasons)
        breakdown.hiring = self._score_hiring(counts, reasons)
        breakdown.product = self._score_product(counts, entity, reasons)
        breakdown.community = self._score_community(counts, reasons)
        breakdown.news = self._score_news(counts, reasons)
        breakdown.github = self._score_github(counts, entity, reasons)
        breakdown.partnership = self._score_partnership(counts, reasons)
        breakdown.customer = self._score_customer(counts, reasons)
        breakdown.momentum = self._score_momentum(entity, reasons)
        breakdown.signal_diversity = self._score_diversity(counts, reasons)
        breakdown.cross_source = self._score_cross_source(entity, reasons)
        breakdown.macro_adjustment = self._score_macro(reasons)

        confidence = self._compute_confidence(entity, counts, reasons)
        types = self._determine_types(breakdown, entity, counts, reasons)

        return ScoredEntity(
            entity=entity,
            score=breakdown,
            confidence=confidence,
            types=types,
            reasons=reasons,
        )

    # --- funding ---

    def _score_funding(self, counts: dict, entity: Entity, reasons: list) -> int:
        funding = counts.get("funding", 0) + counts.get("funding_round", 0)
        if funding == 0 and not entity.funding_history:
            return 0
        if funding == 0 and entity.funding_history:
            funding = 1
        if funding >= 15:
            reasons.append("Major funding round detected")
            return 18
        if funding >= 10:
            reasons.append("Funding event detected")
            return 15
        if funding >= 5:
            reasons.append("Funding activity detected")
            return 11
        reasons.append("Funding signal present")
        return 7

    def _score_smart_money(self, entity: Entity, counts: dict, reasons: list) -> int:
        smart = counts.get("smart_money", 0)
        if smart > 0:
            names = [i.capitalize() for i in entity.investors[:3]]
            label = ", ".join(names) if names else "Notable investors"
            reasons.append(f"Smart money participation ({label})")
            return 8
        if entity.investors:
            reasons.append("Investor participation detected")
            return 5
        return 0

    def _score_accelerator(self, entity: Entity, counts: dict, reasons: list) -> int:
        accel = counts.get("accelerator", 0)
        if accel > 0 or entity.accelerators:
            names = [a.capitalize() for a in entity.accelerators[:2]]
            label = ", ".join(names) if names else "Accelerator"
            reasons.append(f"Accelerator-backed ({label})")
            return 6
        return 0

    # --- growth signals ---

    def _score_hiring(self, counts: dict, reasons: list) -> int:
        hiring = counts.get("hiring", 0)
        if hiring == 0:
            return 0
        if hiring >= 8:
            reasons.append("Significant hiring activity")
            return 10
        if hiring >= 4:
            reasons.append("Active hiring detected")
            return 7
        reasons.append("Hiring signals present")
        return 4

    def _score_product(self, counts: dict, entity: Entity, reasons: list) -> int:
        product = counts.get("product_launch", 0)
        if product == 0:
            return 0
        is_big_tech = entity.name.lower().strip() in BIG_TECH or any(
            bt in entity.name.lower() for bt in BIG_TECH
        )
        has_funding = entity.funding_history or counts.get("funding", 0) or counts.get("funding_round", 0)
        if is_big_tech and not has_funding:
            reasons.append("Product event (major company, lower priority)")
            return 2
        if product >= 5:
            reasons.append("Multiple product launches/events")
            return 10
        if product >= 2:
            reasons.append("Product launch detected")
            return 8
        reasons.append("Product activity detected")
        return 5

    def _score_momentum(self, entity: Entity, reasons: list) -> int:
        progression = [r.get("round") for r in entity.funding_history]
        if len(entity.funding_history) >= 2 and stage_advanced(progression):
            reasons.append("Funding stage progression detected")
            return 7
        if entity.funding_history and (
            entity.total_funding_m or _funding_growth(entity) >= 100
        ):
            reasons.append("Funding momentum (growing rounds)")
            return 5

        entries = self.history.get(entity.id, {}).get("entries", [])
        if len(entries) >= 2:
            prev = entries[-2].get("score", 0) or 0
            curr = entries[-1].get("score", 0) or 0
            if curr > prev >= 0 and (curr - prev) >= 8:
                reasons.append("Score momentum over past days")
                return 6
            if curr > prev:
                reasons.append("Sustained upward trend")
                return 3
        return 0

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
        active = sum(1 for k, v in counts.items() if v > 0 and k not in ("macro_event",))
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

    # --- confidence & types ---

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
        if entity.funding_history:
            confidence += 5
        if entity.investors:
            confidence += 5

        if total_signals < 3:
            confidence -= 15
            reasons.append("Limited data available")

        return max(0, min(100, confidence))

    def _determine_types(self, breakdown: ScoreBreakdown, entity: Entity,
                         counts: dict, reasons: list) -> list[str]:
        types = []
        total = breakdown.total

        has_funding = bool(entity.funding_history) or counts.get("funding", 0) > 0
        growth_signals = (counts.get("hiring", 0) + counts.get("community", 0) +
                          counts.get("customer", 0) + counts.get("momentum", 0))

        stage = entity.startup_stage
        if stage in (PRE_SEED, SEED):
            types.append("EARLY_STAGE")
        elif stage in (SERIES_A, SERIES_B, SERIES_C, GROWTH):
            types.append("GROWTH")

        if has_funding or smart_money_present(entity):
            types.append("VC_BACKED")

        if not has_funding and growth_signals >= 3:
            types.append("PRE_FUNDING")
            types.append("WATCH")

        if entity.ticker or entity.category.lower() in ("public company", "market event", "activist"):
            types.append("PUBLIC_MARKET")

        if counts.get("ma_signal", 0) > 0 or entity.category.lower() in ("m&a", "acquisition", "merger"):
            types.append("M&A_TARGET")

        if total >= 70 and has_funding:
            types.append("INVEST")
        if total >= 60 and growth_signals >= 3:
            types.append("BUILD")
        if total >= 65 and counts.get("community", 0) >= 3:
            types.append("ACQUIRE")
        if not types:
            types.append("WATCH")

        return list(dict.fromkeys(types))


def smart_money_present(entity: Entity) -> bool:
    return bool(entity.investors or entity.accelerators)


def _funding_growth(entity: Entity) -> float:
    return funding_momentum(entity.funding_history)["growth"]