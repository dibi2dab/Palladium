from __future__ import annotations

from src.config import (
    TOP_N, STARTUP_VENTURE_N, PUBLIC_MARKET_N, TECHNOLOGY_N,
    PRODUCT_N, MA_N, MACRO_N, MAX_REPORT_ITEMS,
)
from src.intelligence.scoring import ScoredEntity
from src.intelligence.entities import normalize_name
from src.intelligence import classification

STARTUP_BUCKET = "startup"
PUBLIC_BUCKET = "public"
TECH_BUCKET = "tech"
PRODUCT_BUCKET = "product"
MA_BUCKET = "ma"
MACRO_BUCKET = "macro"

STARTUP_CATS = {
    "startup", "venture", "funding", "private company", "emerging company",
    "investment",
}
PUBLIC_CATS = {"public company", "market event", "activist", "ipo", "etf", "index"}
TECH_CATS = {"ai/ml", "tech", "technology", "open source", "developer tools",
             "backend", "frontend", "security", "database", "automation", "software"}
PRODUCT_CATS = {"product", "saas", "design", "productivity", "fintech",
                "ecommerce", "consumer", "business"}
MA_CATS = {"m&a", "acquisition", "merger", "buyout"}
MACRO_CATS = {"economy", "macro", "macro event", "government", "market event"}

TOP_MIN_SCORE = 70
INCLUDE_MIN_SCORE = 50


def bucket_for(s: ScoredEntity) -> str:
    e = s.entity
    cat = (e.category or "").lower()
    events = set(e.event_types)

    if classification.ACQUISITION in events or cat in MA_CATS:
        return MA_BUCKET

    if classification.MARKET_EVENT in events and cat in MACRO_CATS:
        return MACRO_BUCKET
    if cat in MACRO_CATS and e.entity_type in (classification.OTHER, classification.ORGANIZATION):
        return MACRO_BUCKET

    if e.ticker or e.entity_type == classification.PUBLIC_COMPANY or cat in PUBLIC_CATS:
        return PUBLIC_BUCKET

    if e.entity_type == classification.PRODUCT or cat in PRODUCT_CATS or \
            "producthunt" in (e.tags or []) or "kickstarter" in (e.tags or []):
        return PRODUCT_BUCKET

    if e.entity_type in (classification.STARTUP, classification.PRIVATE_COMPANY) or \
            cat in STARTUP_CATS or bool(e.accelerators) or \
            (e.signal_counts or {}).get("funding_round", 0) > 0 or \
            (e.signal_counts or {}).get("funding", 0) > 0:
        return STARTUP_BUCKET

    if e.entity_type == classification.OPEN_SOURCE_PROJECT or cat in TECH_CATS or \
            (e.signal_counts or {}).get("github", 0) > 0:
        return TECH_BUCKET

    if classification.MARKET_EVENT in events:
        return MACRO_BUCKET

    return TECH_BUCKET


SECTION_SPECS = [
    ("📈 공개시장", PUBLIC_BUCKET, PUBLIC_MARKET_N, "public", "simple"),
    ("🚀 스타트업 & 벤처", STARTUP_BUCKET, STARTUP_VENTURE_N, "venture", "venture"),
    ("🧠 기술", TECH_BUCKET, TECHNOLOGY_N, "tech", "simple"),
    ("🏭 제품 & 비즈니스", PRODUCT_BUCKET, PRODUCT_N, "product", "simple"),
    ("🤝 M&A", MA_BUCKET, MA_N, "ma", "simple"),
    ("🌎 거시경제", MACRO_BUCKET, MACRO_N, "macro", "simple"),
]


def _dupe_key(s: ScoredEntity) -> str:
    n = normalize_name(s.entity.name)
    if not n:
        return s.entity.id
    # Same company, different trailing headline words -> same subject.
    return n[:45]


def build_sections(scored: list[ScoredEntity]) -> list[dict]:
    """Return report sections with quality bands and no forced padding.

    - TOP: scores >= 70 only. Fewer winners → fewer TOP rows.
    - Subject buckets: scores >= 50 only.
    - Total capped at MAX_REPORT_ITEMS. Bad (<50) items never appear.
    """
    ordered = sorted((s for s in scored if s.score.total >= INCLUDE_MIN_SCORE),
                     key=lambda s: s.score.total, reverse=True)

    # Same-name entities (different domains/ids) are the same subject: keep
    # only the highest-scoring representative.
    by_name: dict[str, ScoredEntity] = {}
    for s in ordered:
        key = _dupe_key(s)
        prev = by_name.get(key)
        if prev is None or s.score.total > prev.score.total:
            by_name[key] = s
    ordered = sorted(by_name.values(), key=lambda s: s.score.total, reverse=True)

    top = [s for s in ordered if s.score.total >= TOP_MIN_SCORE][:TOP_N]
    used: set[str] = {s.entity.id for s in top}

    rest: dict[str, list[ScoredEntity]] = {}
    for s in ordered:
        if s.entity.id in used:
            continue
        b = bucket_for(s)
        rest.setdefault(b, []).append(s)

    sections = [{
        "title": "🔥 최우선 투자 기회",
        "items": top,
        "icon": "fire",
        "kind": "top",
    }]

    total = len(top)
    for title, bucket, cap, icon, kind in SECTION_SPECS:
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
            sections.append({
                "title": title,
                "items": items,
                "icon": icon,
                "kind": kind,
            })
    return sections


def total_count(sections: list[dict]) -> int:
    return sum(len(s["items"]) for s in sections)