from __future__ import annotations

from src.intelligence.scoring import ScoredEntity, JUDGEMENT_LABELS
from src.intelligence.classification import ENTITY_TYPE_LABELS, EVENT_TYPE_LABELS
from src.intelligence.funding import STAGE_LABELS_KO, format_amount_kr


def format_reasons(scored: ScoredEntity) -> list[str]:
    """Reasons already carry Korean text produced by the scorer."""
    return list(scored.reasons)


_REASON_LABELS = {
    "funding": "투자",
    "smart_money": "주요 투자자",
    "accelerator": "액셀러레이터",
    "hiring": "채용",
    "product": "제품",
    "momentum": "성장 모멘텀",
    "community": "커뮤니티",
    "news": "뉴스",
    "github": "GitHub",
    "partnership": "파트너십",
    "customer": "고객",
    "signal_diversity": "신호 다양성",
    "cross_source": "교차 출처",
    "macro_adjustment": "거시경제",
}


def format_score_change(prev: int, curr: int) -> str:
    change = curr - prev
    if change > 0:
        return f"{prev} → {curr} (+{change})"
    elif change < 0:
        return f"{prev} → {curr} ({change})"
    return f"{prev} → {curr}"


def _stage_label(startup_stage: str) -> str:
    return STAGE_LABELS_KO.get(startup_stage, "")


def _funding_status_label(status: str) -> str:
    return {
        "confirmed": "투자 확정",
        "planned": "투자 계획",
        "withdrawn": "투자 무산/철회",
    }.get(status, "")