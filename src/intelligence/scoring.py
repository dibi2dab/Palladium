from __future__ import annotations

import logging
from dataclasses import dataclass, field

from src.intelligence.entities import Entity, EntityManager
from src.intelligence.signals import SignalManager
from src.intelligence.funding import (
    PRE_SEED, SEED, SERIES_A, SERIES_B, SERIES_C, GROWTH,
    UNKNOWN, BIG_TECH, funding_momentum, stage_advanced,
)
from src.intelligence import classification
from src.report.narrative import build_narrative

logger = logging.getLogger(__name__)


# Macro event base effects, only applied when the entity is relevant.
MACRO_BOOSTS = {
    "rate_cut": 5,
    "rate_hike": -4,
    "cpi_low": 3,
    "cpi_high": -3,
    "gdp_growth": 3,
    "gdp_decline": -3,
    "employment_strong": 2,
    "employment_weak": -2,
    "oil_price_up": -3,
    "oil_price_down": 2,
}

# Judgements (bands)
PRIORITY = "PRIORITY"
ATTENTION = "ATTENTION"
WATCH = "WATCH"
EXCLUDED = "EXCLUDED"

JUDGEMENT_LABELS = {
    PRIORITY: "🔥 최우선 기회",
    ATTENTION: "🚀 주목",
    WATCH: "👀 관찰",
    EXCLUDED: "제외",
}

MAINSTREAM_SOURCES = [
    "techcrunch", "reuters", "bloomberg", "theverge", "the verge", "cnbc",
    "axios", "fortune", "wsj", "ft ", "financial times", "forbes", "business insider",
    "techcrunch.com", "venturebeat", "eu-startups", "tech.eu", "arne", "arstechnica",
]


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
            ("funding", self.funding),
            ("smart_money", self.smart_money),
            ("accelerator", self.accelerator),
            ("hiring", self.hiring),
            ("product", self.product),
            ("momentum", self.momentum),
            ("community", self.community),
            ("news", self.news),
            ("github", self.github),
            ("partnership", self.partnership),
            ("customer", self.customer),
        ]
        return [(k, v) for k, v in items if v > 0]


@dataclass
class ScoredEntity:
    entity: Entity
    score: ScoreBreakdown
    confidence: int = 0
    news_importance: int = 0
    entity_type: str = classification.OTHER
    event_types: list[str] = field(default_factory=list)
    judgement: str = EXCLUDED
    reasons: list[str] = field(default_factory=list)
    conf_evidence: list[str] = field(default_factory=list)
    narrative: dict = field(default_factory=dict)
    previous_score: int = 0
    score_change: int = 0

    @classmethod
    def new_from(cls, scored: "ScoredEntity") -> "ScoredEntity":
        # lightweight copy used in tests/serialization
        return cls(
            entity=scored.entity,
            score=scored.score,
            confidence=scored.confidence,
            news_importance=scored.news_importance,
            entity_type=scored.entity_type,
            event_types=list(scored.event_types),
            judgement=scored.judgement,
            reasons=list(scored.reasons),
            conf_evidence=list(scored.conf_evidence),
            narrative=dict(scored.narrative),
            previous_score=scored.previous_score,
            score_change=scored.score_change,
        )


def judge(total: int) -> str:
    if total >= 80:
        return PRIORITY
    if total >= 70:
        return ATTENTION
    if total >= 50:
        return WATCH
    return EXCLUDED


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
            results.append(self._score_entity(entity))
        results.sort(key=lambda s: s.score.total, reverse=True)
        return results

    def _score_entity(self, entity: Entity) -> ScoredEntity:
        breakdown = ScoreBreakdown()
        reasons: list[str] = []

        counts = self.signals.count_by_category(entity.id, days=30)

        breakdown.funding = self._score_funding(counts, entity, reasons)
        breakdown.smart_money = self._score_smart_money(entity, reasons)
        breakdown.accelerator = self._score_accelerator(entity, reasons)
        breakdown.hiring = self._score_hiring(counts, reasons)
        breakdown.product = self._score_product(counts, entity, reasons)
        breakdown.community = self._score_community(counts, reasons)
        breakdown.news = self._score_news(counts, reasons)
        breakdown.github = self._score_github(counts, entity, reasons)
        breakdown.partnership = self._score_partnership(counts, reasons)
        breakdown.customer = self._score_customer(counts, reasons)
        breakdown.momentum = self._score_momentum(entity, reasons)
        breakdown.signal_diversity = self._score_diversity(counts, entity, reasons)
        breakdown.cross_source = self._score_cross_source(entity, reasons)
        breakdown.macro_adjustment = self._score_macro(entity, breakdown, reasons)

        confidence, evidence = self._compute_confidence(entity, counts)
        news_importance = self._news_importance(entity, counts)
        total = breakdown.total
        judgement = judge(total)
        narrative = build_narrative(
            entity, breakdown, entity.event_types, entity.startup_stage, judgement,
        )

        return ScoredEntity(
            entity=entity,
            score=breakdown,
            confidence=confidence,
            news_importance=news_importance,
            entity_type=entity.entity_type,
            event_types=list(entity.event_types),
            judgement=judgement,
            reasons=reasons,
            conf_evidence=evidence,
            narrative=narrative,
        )

    # --- funding (confirmed events only) ---

    def _score_funding(self, counts: dict, entity: Entity, reasons: list) -> int:
        withdrawn = counts.get("funding_withdrawn", 0)
        confirmed_active = counts.get("funding_round", 0) + counts.get("funding", 0)

        confirmed_history = [r for r in entity.funding_history
                             if r.get("status", "confirmed") == "confirmed"]
        if entity.funding_status == "withdrawn":
            # A scrubbed/cancelled round is not a positive signal; a company
            # whose latest funding event was cancelled does not earn funding
            # points at all, regardless of older confirmed rounds.
            reasons.append("최근 투자 무산/철회 이벤트 감지 — 투자 점수 없음")
            return 0
        if confirmed_active == 0 and not confirmed_history:
            if withdrawn:
                reasons.append("투자 무산/철회 이벤트 (긍정 신호 아님)")
            return 0

        points = 24
        if confirmed_active >= 3:
            points += 8
            reasons.append("다수의 투자 유치 신호/출처")
        elif confirmed_active >= 2:
            points += 5
            reasons.append("복수의 투자 유치 신호")

        amounts = [r.get("amount_m") for r in confirmed_history if r.get("amount_m")]
        if amounts:
            latest = max(amounts)
            if latest >= 500:
                points += 14
                reasons.append("초대형 투자 유치 (5억 달러 이상 추정)")
            elif latest >= 100:
                points += 10
                reasons.append("대규모 투자 유치 (1억 달러 이상 추정)")
            elif latest >= 25:
                points += 6
                reasons.append("상당 규모 투자 유치 (2,500만 달러 이상)")

        distinct_rounds = {r.get("round") for r in confirmed_history if r.get("round") and r.get("round") != UNKNOWN}
        if len(distinct_rounds) >= 2:
            points += 5
            reasons.append("여러 투자 단계 확인 (연속 투자)")
        elif len(confirmed_history) > 1:
            points += 3
            reasons.append("다수의 확정 투자 기록")
        else:
            reasons.append("투자 유치 신호")

        return min(50, points)

    def _score_smart_money(self, entity: Entity, reasons: list) -> int:
        if entity.investors:
            names = [i.capitalize() for i in entity.investors[:3]]
            reasons.append(f"주요 투자자 참여 ({', '.join(names)})")
            return 12
        return 0

    def _score_accelerator(self, entity: Entity, reasons: list) -> int:
        if entity.accelerators:
            names = [a.capitalize() for a in entity.accelerators[:2]]
            reasons.append(f"액셀러레이터 출신 ({', '.join(names)})")
            return 8
        return 0

    # --- growth signals ---

    def _score_hiring(self, counts: dict, reasons: list) -> int:
        hiring = counts.get("hiring", 0)
        if hiring == 0:
            return 0
        if hiring >= 8:
            reasons.append("채용 크게 확대")
            return 10
        if hiring >= 4:
            reasons.append("채용 활동 증가")
            return 7
        reasons.append("채용 신호")
        return 4

    def _score_product(self, counts: dict, entity: Entity, reasons: list) -> int:
        product = counts.get("product_launch", 0)
        if product == 0:
            return 0
        is_big_tech = entity.name.lower().strip() in BIG_TECH or any(
            bt.strip() in entity.name.lower() for bt in BIG_TECH if bt.strip()
        )
        has_funding = bool(entity.funding_history) or counts.get("funding", 0) or counts.get("funding_round", 0)
        if is_big_tech and not has_funding:
            reasons.append("제품 이벤트 (대기업, 투자 관점 우선순위 낮음)")
            return 2
        if product >= 5:
            reasons.append("여러 제품 출시/이벤트")
            return 8
        if product >= 2:
            reasons.append("제품 출시 감지")
            return 6
        reasons.append("제품 이벤트")
        return 4

    def _score_momentum(self, entity: Entity, reasons: list) -> int:
        confirmed = [r for r in entity.funding_history
                     if r.get("status", "confirmed") == "confirmed"]
        progression = [r.get("round") for r in confirmed]
        if len(confirmed) >= 2 and stage_advanced(progression):
            reasons.append("투자 단계 상승 (시드 → 시리즈 등)")
            return 7
        if confirmed and (entity.total_funding_m or _funding_growth(entity) >= 100):
            reasons.append("투자 규모 증가 추세")
            return 5

        entries = self.history.get(entity.id, {}).get("entries", [])
        if len(entries) >= 2:
            prev = entries[-2].get("score", 0) or 0
            curr = entries[-1].get("score", 0) or 0
            if curr > prev >= 0 and (curr - prev) >= 8:
                reasons.append("최근 점수 가속 상승")
                return 6
            if curr > prev:
                reasons.append("점수 상승 추세")
                return 3
        return 0

    def _score_community(self, counts: dict, reasons: list) -> int:
        community = counts.get("community", 0)
        if community == 0:
            return 0
        if community >= 8:
            reasons.append("커뮤니티 관심 급증")
            return 6
        if community >= 3:
            reasons.append("커뮤니티 활동 증가")
            return 4
        reasons.append("커뮤니티 신호")
        return 2

    def _score_news(self, counts: dict, reasons: list) -> int:
        news = counts.get("news", 0)
        if news == 0:
            return 0
        if news >= 10:
            reasons.append("언론 보도 증가")
            return 4
        if news >= 5:
            reasons.append("언론 보도 확인")
            return 3
        reasons.append("언론 언급")
        return 2

    def _score_github(self, counts: dict, entity: Entity, reasons: list) -> int:
        github = counts.get("github", 0)
        if github == 0 and not entity.github:
            return 0
        if github >= 5:
            reasons.append("GitHub 활동 강함")
            return 6
        if github >= 2 or entity.github:
            reasons.append("GitHub 활동 감지")
            return 4
        return 2

    def _score_partnership(self, counts: dict, reasons: list) -> int:
        p = counts.get("partnership", 0)
        if p >= 3:
            reasons.append("파트너십 다수 확인")
            return 6
        if p >= 1:
            reasons.append("파트너십 체결")
            return 3
        return 0

    def _score_customer(self, counts: dict, reasons: list) -> int:
        c = counts.get("customer", 0)
        if c >= 5:
            reasons.append("고객 확보 다수")
            return 8
        if c >= 2:
            reasons.append("고객/매출 신호")
            return 5
        if c >= 1:
            reasons.append("고객 신호")
            return 3
        return 0

    # --- diversity: distinct SIGNAL TYPES, not article count ---

    def _score_diversity(self, counts: dict, entity: Entity, reasons: list) -> int:
        # funding_round and funding are the same underlying signal type.
        merged = dict(counts)
        if entity.funding_status == "withdrawn":
            merged["funding"] = 0
            merged["funding_round"] = 0
        if merged.get("funding", 0) > 0 and merged.get("funding_round", 0) > 0:
            merged["funding"] = merged.get("funding", 0) + merged.get("funding_round", 0)
            merged["funding_round"] = 0
        active = sum(
            1 for k, v in merged.items()
            if v > 0 and k not in ("macro_event",)
        )
        if active >= 4:
            reasons.append(f"확인된 성장 신호: {active}종")
            return 12
        if active == 3:
            reasons.append(f"확인된 성장 신호: {active}종")
            return 9
        if active == 2:
            reasons.append(f"확인된 성장 신호: {active}종")
            return 6
        if active == 1:
            return 1
        return 0

    # --- cross-source: distinct outlets for the same (main) event ---

    def _score_cross_source(self, entity: Entity, reasons: list) -> int:
        source_counts = self.signals.source_count_by_category(entity.id, days=30)
        # treat funding + funding_round as one event
        if entity.funding_status != "withdrawn" and (
                source_counts.get("funding_round", 0) or source_counts.get("funding", 0)):
            merged_sources = set()
            active = self.signals.get_recent_signals(entity.id, days=30)
            for s in active:
                if s.category in ("funding", "funding_round"):
                    merged_sources.update(s.sources or [s.source])
            source_counts["funding"] = max(len(merged_sources),
                                           source_counts.get("funding", 0) + source_counts.get("funding_round", 0))
        if entity.funding_status == "withdrawn":
            source_counts["funding"] = 0
            source_counts["funding_round"] = 0
        main_sources = 0
        for cat, cnt in source_counts.items():
            if cat in ("macro_event", "news"):
                continue
            main_sources = max(main_sources, cnt)
        if main_sources >= 4:
            reasons.append(f"교차 출처 확인: {main_sources}곳")
            return 12
        if main_sources == 3:
            reasons.append(f"교차 출처 확인: {main_sources}곳")
            return 9
        if main_sources == 2:
            reasons.append(f"교차 출처 확인: {main_sources}곳")
            return 6
        unique_sources = len(set(entity.signal_sources))
        if unique_sources == 1 and entity.signal_sources:
            reasons.append("단일 출처")
            return 0
        return 0

    # --- macro: applied ONLY when relevant to the entity ---

    def _score_macro(self, entity: Entity, breakdown: ScoreBreakdown,
                     reasons: list) -> int:
        if not self.macro_events:
            return 0
        entity_text = f"{entity.name} {entity.category} {' '.join(entity.tags)}"
        adjustment = 0
        touched = False
        for event in self.macro_events:
            etype = event.get("type", "")
            if etype not in MACRO_BOOSTS:
                continue
            rel = classification.macro_relevance_score(etype, entity_text)
            if rel == 0:
                continue
            touched = True
            base = MACRO_BOOSTS[etype]
            # Broad macro indicators (GDP, employment) have weak baseline effect.
            if event.get("broad"):
                base = base // 2
            adjustment += base
        adjustment = max(-10, min(10, adjustment))
        if adjustment > 0:
            reasons.append("관련 거시경제 순풍 확인")
        elif adjustment < 0:
            reasons.append("관련 거시경제 역풍 (해당 산업 관련)")
        elif touched and breakdown.total >= 40:
            reasons.append("거시경제 영향: 낮음 (산업 관련성 낮음)")
        return adjustment

    # --- news importance (separate from opportunity score) ---

    def _news_importance(self, entity: Entity, counts: dict) -> int:
        imp = 10
        name_l = entity.name.lower()
        if entity.ticker:
            imp += 25
        if entity.entity_type in (classification.PUBLIC_COMPANY,):
            imp += 20
        if name_l.strip() in BIG_TECH or any(
                bt.strip() in name_l for bt in BIG_TECH if bt.strip()):
            imp += 25
        events = set(entity.event_types)
        if events & {classification.EARNINGS, classification.IPO, classification.REGULATORY}:
            imp += 20
        if classification.ACQUISITION in events:
            imp += 20
        news = counts.get("news", 0)
        imp += min(news * 2, 20)
        return max(0, min(100, imp))

    # --- confidence with evidence ---

    def _compute_confidence(self, entity: Entity, counts: dict) -> tuple[int, list[str]]:
        confidence = 25
        evidence: list[str] = []
        unique_sources = set(entity.signal_sources)

        src_names = _source_names(entity)
        mainstream = [s for s in src_names if _is_mainstream(s)]
        official = [s for s in src_names
                    if _is_official_source(s, entity.domain) and not _is_mainstream(s)]

        if unique_sources:
            confidence += min(len(unique_sources) * 8, 24)
            evidence.append(f"출처 {len(unique_sources)}곳")
        if mainstream:
            confidence += 8
            evidence.append("주류 언론 보도")
        if official:
            confidence += 10
            evidence.append("회사 공식 채널/공식 도메인")

        amount_in_title = False
        for s in self.signals.get_recent_signals(entity.id, days=30):
            if s.category in ("funding_round", "funding", "smart_money") and s.description:
                if any(k in s.description for k in ("M", "B", "billion", "million", "$")):
                    amount_in_title = True
        if entity.funding_history or amount_in_title:
            confidence += 8
            evidence.append("구조화된 투자 데이터")

        if entity.investors:
            confidence += 5
        if entity.accelerators:
            confidence += 4

        total_signals = sum(counts.values())
        if total_signals < 3:
            confidence -= 15
            evidence.append("데이터 제한적")
        else:
            confidence += 5

        if entity.funding_status == "withdrawn":
            confidence -= 20
            evidence.append("투자 무산/철회 확인")

        if entity.startup_stage != UNKNOWN:
            # low stage confidence from conflicting sources
            if any(r.get("round") and r.get("round") != entity.startup_stage
                   for r in entity.funding_history):
                confidence -= 10
                evidence.append("투자 단계 출처 간 불일치")

        return max(0, min(100, confidence)), evidence


def _source_names(entity: Entity) -> list[str]:
    names = []
    for s in entity.signal_sources:
        name = s.split(":")[-1].strip()
        names.append(name)
    return [n for n in names if n]


def _is_mainstream(src: str) -> bool:
    s = src.lower()
    return any(m in s for m in MAINSTREAM_SOURCES)


def _is_official_source(src: str, domain: str) -> bool:
    if not domain:
        return False
    return domain in src or src.lower() in ("ycombinator", "sec_edgar", "fred")


def smart_money_present(entity: Entity) -> bool:
    return bool(entity.investors or entity.accelerators)


def _funding_growth(entity: Entity) -> float:
    return funding_momentum(entity.funding_history)["growth"]