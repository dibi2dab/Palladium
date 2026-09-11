"""Second-Order Opportunities (2차 기회) — rule-based starter.

Derives possible follow-on opportunities from OBSERVED signals (top entities
or macro events). Always framed as derived/potential, never fabricated
numbers. Chain map lives in config/scoring.yml.
"""
from __future__ import annotations

from src.intelligence.scoring import ScoredEntity
from src.palladium_config import second_order_chains, macro_second_order

# trigger keyword → chain key
_TRIGGER_KEYS = [
    ("ai", ["ai ", "인공지능", "llm", "gpt", "모델"]),
    ("gpu", ["gpu", "가속기", "h100", "a100"]),
    ("semiconductor", ["반도체", "semiconductor", "칩", "팹"]),
    ("battery", ["배터리", "battery", "ess", "리튬"]),
    ("ev", ["전기차", "ev", "전동화"]),
    ("robotics", ["로봇", "robotics", "humanoid"]),
    ("data", ["데이터", "data", "빅데이터"]),
    ("cloud", ["클라우드", "cloud", "데이터센터", "data center"]),
]


def _chain_key(entity_text: str) -> str | None:
    t = (entity_text or "").lower()
    for key, triggers in _TRIGGER_KEYS:
        if any(tr in t for tr in triggers):
            return key
    return None


def detect_second_order(scored: list[ScoredEntity], macro_events: list[dict]) -> list[dict]:
    """Return derived second-order opportunities.

    Each item: {
        "trigger": observed subject,
        "url": external url or "",
        "status": "Derived" or "Macro",
        "chain": [possible follow-on opportunities],
    }
    """
    results: list[dict] = []
    seen: set[str] = set()

    chains = second_order_chains()
    for s in scored:
        if s.score.total < 70:
            continue
        text = f"{s.entity.name} {s.entity.category} {s.entity.description}"
        key = _chain_key(text)
        if key is None or key not in chains:
            continue
        if key in seen:
            continue
        seen.add(key)
        results.append({
            "trigger": s.entity.name,
            "url": s.entity.url or "",
            "status": "Derived",
            "chain": chains.get(key, []),
        })

    macro_map = macro_second_order()
    for event in macro_events:
        etype = event.get("type", "")
        notes = macro_map.get(etype)
        if not notes:
            continue
        trigger = f"거시경제: {etype}"
        results.append({
            "trigger": trigger,
            "url": "",
            "status": "Macro",
            "chain": notes,
        })

    return results