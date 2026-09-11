"""Cross-signal convergence.

A CONVERGENCE_SIGNAL means several DIFFERENT kinds of active signals point at
the same entity: >=3 distinct categories, with >=2 of them being strong
growth categories, backed by >=2 distinct sources. Rules only.
"""
from __future__ import annotations

from src.intelligence.entities import Entity
from src.palladium_config import convergence_rules

CONVERGENCE_CATEGORY_LABELS = {
    "funding": "투자 유치",
    "funding_round": "투자 유치",
    "hiring": "채용",
    "github": "개발 활동",
    "product_launch": "제품 출시",
    "community": "커뮤니티",
    "customer": "고객/매출",
    "partnership": "파트너십",
    "news": "언론 보도",
    "market_event": "시장 이벤트",
}


def convergence_categories(entity: Entity, counts: dict) -> list[str]:
    """Return the active strong categories implying a convergence signal.

    Returns [] when there is no convergence.
    """
    rules = convergence_rules()
    strong = rules.get("strong_categories", [])
    min_distinct = rules.get("min_distinct_signals", 3)
    min_strong = rules.get("min_strong_signals", 2)

    # funding + funding_round are the same underlying signal.
    merged = dict(counts or {})
    if merged.get("funding", 0) and merged.get("funding_round", 0):
        merged["funding"] = merged.get("funding", 0) + merged.get("funding_round", 0)
        merged["funding_round"] = 0

    active = {c for c, v in merged.items() if v and c != "macro_event"}
    strong_active = [c for c in strong if merged.get(c, 0)]

    if len(active) >= min_distinct and len(strong_active) >= min_strong:
        return strong_active
    return []


def convergence_label(cat: str) -> str:
    return CONVERGENCE_CATEGORY_LABELS.get(cat, cat)