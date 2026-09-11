"""Evidence Quality — how trustworthy is the underlying data for an entity.

Very high(공식 공시/API) > High(주요 언론/공식 채널) > Medium(보도·커뮤니티)
> Low(1차 출처/미확인). Implemented as rules only — no AI.
"""
from __future__ import annotations

from src.intelligence.entities import Entity
from src.palladium_config import source_reliability, official_domain_suffixes

VERY_HIGH = "VERY_HIGH"
HIGH = "HIGH"
MEDIUM = "MEDIUM"
LOW = "LOW"

QUALITY_LABELS = {
    VERY_HIGH: "공식 공시·API 수준",
    HIGH: "주요 언론·공식 채널",
    MEDIUM: "보도·커뮤니티 수준",
    LOW: "미확인·1차 출처",
}

ORDER = [VERY_HIGH, HIGH, MEDIUM, LOW]


def quality_label(code: str) -> str:
    return QUALITY_LABELS.get(code, MEDIUM)


def _split_source(src: str) -> str:
    return (src or "").split(":")[-1].strip().lower()


def _tier_of(src: str, domain: str) -> str | None:
    """Return the reliability tier for a single source name."""
    s = _split_source(src)
    if not s:
        return None

    rel = source_reliability()
    for tier in ORDER:
        for marker in rel.get(tier, []):
            if marker in s:
                return tier

    # Official corporate domains (korea .kr / gov / org) are HIGH evidence.
    if domain:
        d = domain.lower().replace("www.", "")
        suffixes = official_domain_suffixes()
        if any(d.endswith(suf) for suf in suffixes):
            return HIGH
    return None


def evidence_quality(entity: Entity, source_names: list[str] | None = None) -> str:
    """Compute the evidence-quality tier for an entity (code string)."""
    srcs = source_names if source_names is not None else (entity.signal_sources or [])
    tiers: list[str] = []
    for src in srcs:
        t = _tier_of(src, entity.domain or "")
        if t:
            tiers.append(t)

    if not tiers:
        # Structured, machine-confirmed data is still evidence even if the
        # source tag itself could not be tiered.
        if entity.funding_history or entity.events:
            return MEDIUM
        return LOW

    if VERY_HIGH in tiers and HIGH not in tiers:
        # A single official filing is strong, but not '공식 공시 수준'.
        return HIGH if len(tiers) == 1 else VERY_HIGH

    if VERY_HIGH in tiers:
        return VERY_HIGH
    if HIGH in tiers:
        return HIGH
    if LOW in tiers and MEDIUM not in tiers:
        return LOW
    return MEDIUM