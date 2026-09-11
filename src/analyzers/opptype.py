"""Opportunity Type (INVEST / BUILD / ACQUIRE / WATCH / IGNORE).

A rule-based classification of WHAT the report is telling a reader to do.
Runs on top of the existing score/judgement bands.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from src.intelligence import classification
from src.palladium_config import score_bands

if TYPE_CHECKING:
    from src.intelligence.scoring import ScoredEntity

INVEST = "INVEST"
BUILD = "BUILD"
ACQUIRE = "ACQUIRE"
WATCH = "WATCH"
IGNORE = "IGNORE"

OPP_TYPE_LABELS = {
    INVEST: "투자",
    BUILD: "구축·진입",
    ACQUIRE: "인수",
    WATCH: "관찰",
    IGNORE: "제외",
}


def opp_type_label(code: str) -> str:
    return OPP_TYPE_LABELS.get(code, WATCH)


def opportunity_type(scored: ScoredEntity) -> str:
    if scored.score.total < score_bands().get("include_min_score", 50):
        return IGNORE

    e = scored.entity
    events = set(e.event_types)

    if classification.ACQUISITION in events:
        return ACQUIRE
    if e.entity_type in (classification.STARTUP, classification.PRIVATE_COMPANY):
        if e.ticker:
            return WATCH
        return INVEST
    if e.entity_type in (classification.PRODUCT, classification.OPEN_SOURCE_PROJECT):
        if e.funding_history or e.funding_status in ("confirmed", "planned"):
            return INVEST
        return BUILD
    if classification.MARKET_EVENT in events or e.entity_type == classification.PUBLIC_COMPANY:
        return WATCH
    return WATCH