from __future__ import annotations

from src.intelligence.scoring import ScoredEntity


def format_reasons(scored: ScoredEntity) -> list[str]:
    reasons = []
    breakdown = scored.score

    if breakdown.funding > 0:
        reasons.append(f"Funding signal (+{breakdown.funding})")
    if breakdown.hiring > 0:
        reasons.append(f"Hiring activity (+{breakdown.hiring})")
    if breakdown.product > 0:
        reasons.append(f"Product event (+{breakdown.product})")
    if breakdown.community > 0:
        reasons.append(f"Community engagement (+{breakdown.community})")
    if breakdown.news > 0:
        reasons.append(f"News coverage (+{breakdown.news})")
    if breakdown.github > 0:
        reasons.append(f"GitHub activity (+{breakdown.github})")
    if breakdown.partnership > 0:
        reasons.append(f"Partnership (+{breakdown.partnership})")
    if breakdown.customer > 0:
        reasons.append(f"Customer traction (+{breakdown.customer})")
    if breakdown.signal_diversity > 0:
        reasons.append(f"Diverse signals ({breakdown.signal_diversity})")
    if breakdown.cross_source > 0:
        reasons.append(f"Cross-source confirmation (+{breakdown.cross_source})")
    if breakdown.macro_adjustment > 0:
        reasons.append(f"Macro tailwind (+{breakdown.macro_adjustment})")
    elif breakdown.macro_adjustment < 0:
        reasons.append(f"Macro headwind ({breakdown.macro_adjustment})")

    return reasons


def format_score_change(prev: int, curr: int) -> str:
    change = curr - prev
    if change > 0:
        return f"{prev} → {curr} (+{change})"
    elif change < 0:
        return f"{prev} → {curr} ({change})"
    return f"{prev} → {curr}"
