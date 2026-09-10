from __future__ import annotations

from src.config import (
    TOP_N, STARTUP_VENTURE_N, PUBLIC_MARKET_N, TECHNOLOGY_N,
    PRODUCT_N, MA_N, MACRO_N, MAX_REPORT_ITEMS,
)
from src.intelligence.scoring import ScoredEntity

STARTUP_BUCKET = "startup"
PUBLIC_BUCKET = "public"
TECH_BUCKET = "tech"
PRODUCT_BUCKET = "product"
MA_BUCKET = "ma"
MACRO_BUCKET = "macro"


STARTUP_CATS = {
    "startup", "venture", "funding", "private company", "emerging company",
    "investment", "funding event",
}

PUBLIC_CATS = {
    "public company", "market event", "activist", "ipo", "etf", "index",
}

TECH_CATS = {
    "ai/ml", "tech", "technology", "open source", "developer tools",
}

PRODUCT_CATS = {
    "product", "business", "ecommerce", "consumer", "saas tool",
}

MA_CATS = {
    "m&a", "acquisition", "merger", "buyout",
}

MACRO_CATS = {
    "economy", "macro", "macro event", "government",
}


def bucket_for(s: ScoredEntity) -> str:
    e = s.entity
    cat = (e.category or "").lower()
    types = s.types

    if "M&A_TARGET" in types or cat in MA_CATS:
        return MA_BUCKET

    if e.ticker or cat in PUBLIC_CATS or "PUBLIC_MARKET" in types or \
            any(t in ("market", "stock", "equity") for t in (e.tags or [])):
        return PUBLIC_BUCKET

    if cat in MACRO_CATS or "macro_event" in (e.signal_counts or {}):
        return MACRO_BUCKET

    is_startupish = (
        cat in STARTUP_CATS
        or e.startup_stage != "UNKNOWN"
        or bool(e.accelerators)
        or ("yc" in (e.tags or []) or "startup" in (e.tags or []))
        or any(t in ("EARLY_STAGE", "GROWTH", "VC_BACKED", "PRE_FUNDING") for t in types)
        or (e.signal_counts or {}).get("funding_round", 0) > 0
        or (e.signal_counts or {}).get("funding", 0) > 0
    )
    if is_startupish:
        return STARTUP_BUCKET

    if cat in TECH_CATS or (e.signal_counts or {}).get("github", 0) > 0:
        return TECH_BUCKET

    if cat in PRODUCT_CATS:
        return PRODUCT_BUCKET

    return TECH_BUCKET


SECTION_SPECS = [
    ("PUBLIC MARKET", PUBLIC_BUCKET, PUBLIC_MARKET_N, "public"),
    ("STARTUP & VENTURE", STARTUP_BUCKET, STARTUP_VENTURE_N, "venture"),
    ("TECHNOLOGY", TECH_BUCKET, TECHNOLOGY_N, "tech"),
    ("PRODUCT / BUSINESS", PRODUCT_BUCKET, PRODUCT_N, "product"),
    ("M&A", MA_BUCKET, MA_N, "ma"),
    ("MACRO", MACRO_BUCKET, MACRO_N, "macro"),
]


def build_sections(scored: list[ScoredEntity]) -> list[dict]:
    """Return report sections: [{title, items, icon, kind}].

    First TOP_N best opportunities (any bucket) form the TOP section.
    Remaining items fill each subject section, excluding already-shown
    entities, up to MAX_REPORT_ITEMS total (no duplicates).
    """
    ordered = sorted(scored, key=lambda s: s.score.total, reverse=True)
    top = ordered[:TOP_N]
    used: set[str] = {s.entity.id for s in top}

    rest: dict[str, list[ScoredEntity]] = {}
    for s in ordered[TOP_N:]:
        if s.score.total <= 0:
            continue
        b = bucket_for(s)
        rest.setdefault(b, []).append(s)

    sections = [{
        "title": "TOP INVESTMENT OPPORTUNITIES",
        "items": top,
        "icon": "fire",
        "kind": "top",
    }]

    total = len(top)
    for title, bucket, cap, icon in SECTION_SPECS:
        if total >= MAX_REPORT_ITEMS:
            break
        items = []
        for s in rest.get(bucket, []):
            if s.entity.id in used:
                continue
            items.append(s)
            used.add(s.entity.id)
            total += 1
            if len(items) >= cap or total >= MAX_REPORT_ITEMS:
                break
        if items:
            kind = "venture" if bucket == STARTUP_BUCKET else "simple"
            sections.append({
                "title": title,
                "items": items,
                "icon": icon,
                "kind": kind,
            })

    return sections


def total_count(sections: list[dict]) -> int:
    return sum(len(s["items"]) for s in sections)