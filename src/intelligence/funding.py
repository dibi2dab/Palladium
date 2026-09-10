from __future__ import annotations

import re
from datetime import date


# Startup funding stages
PRE_SEED = "PRE_SEED"
SEED = "SEED"
SERIES_A = "SERIES_A"
SERIES_B = "SERIES_B"
SERIES_C = "SERIES_C"
GROWTH = "GROWTH"
PUBLIC = "PUBLIC"
UNKNOWN = "UNKNOWN"

STAGE_LABELS = {
    PRE_SEED: "Pre-Seed",
    SEED: "Seed",
    SERIES_A: "Series A",
    SERIES_B: "Series B",
    SERIES_C: "Series C",
    GROWTH: "Growth / Late",
    PUBLIC: "Public",
    UNKNOWN: "Unknown",
}

# Round keywords in priority order
ROUND_PATTERNS = [
    ("pre-seed", PRE_SEED),
    ("pre seed", PRE_SEED),
    ("seed round", SEED),
    ("seed", SEED),
    ("series a", SERIES_A),
    ("series b", SERIES_B),
    ("series c", SERIES_C),
    ("series d", GROWTH),
    ("series e", GROWTH),
    ("growth round", GROWTH),
    ("late-stage", GROWTH),
    ("ipo", PUBLIC),
    ("spac", PUBLIC),
]

# Well-known investors / accelerators (smart money detection)
KNOWN_VCS = [
    "a16z", "andreessen horowitz", "sequoia capital", "sequoia",
    "y combinator", "accel", "founders fund", "benchmark",
    "lightspeed venture", "lightspeed", "greylock", "index ventures",
    "nea", "new enterprise associates", "bessemer venture",
    "khosla ventures", "insight partners", "tiger global",
    "softbank", "vision fund", "general catalyst", "google ventures",
    "gv ", "iconiq", "coatue", "dragoneer", "kleiner perkins",
    "menlo ventures", "crv ", "first round capital", "sv angel",
    "battery ventures", "ivp", "thrive capital", "bain capital ventures",
    "true ventures", "felicis", "amplify partners", "redpoint",
    "usv", "union square ventures", "a16z", "accel partners",
    "peak xv", "greenoaks", "hospitality",
]

ACCELERATORS = [
    "y combinator", "techstars", "500 global", "antler", "500 startups",
    "plug and play", "masschallenge", "alchemist accelerator", "data collective",
]

# Large public companies whose ordinary product news should NOT dominate
BIG_TECH = [
    "apple", "google", "alphabet", "microsoft", "meta ", "facebook",
    "amazon", "samsung", "tesla", "openai", "nvidia", "netflix",
    "intel", "ibm", "oracle", "salesforce", "adobe", "amazon",
    "uber", "airbnb", "twitter", "linkedin", "snap", "palantir",
    "anthropic", "microsoft", "x corp",
]

AMOUNT_RE = re.compile(
    r"\$\s?([0-9][0-9,\.]*)\s?(m|mn|million|k|kilo|b|bn|billion)\b",
    re.IGNORECASE,
)


def normalize_text(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text or "").replace("\xa0", " ")


def parse_amount(text: str) -> float | None:
    """Extract a USD amount, normalized to millions (e.g. 3.5 for $3.5M)."""
    t = normalize_text(text)
    m = AMOUNT_RE.search(t)
    if not m:
        return None
    try:
        val = float(m.group(1).replace(",", ""))
    except ValueError:
        return None
    unit = m.group(2).lower()
    if unit in ("b", "bn", "billion"):
        val *= 1000.0
    elif unit in ("k", "kilo", "thousand"):
        val /= 1000.0
    return round(val, 2)


def detect_round(text: str) -> tuple[str, str] | None:
    """Return (stage, matched_round_text) or None."""
    t = (normalize_text(text) or "").lower()
    for pattern, stage in ROUND_PATTERNS:
        if pattern in t:
            return stage, pattern
    return None


def detect_investors(text: str) -> list[str]:
    """Return known investors/accelerators found in text (dedup, keep order)."""
    t = (text or "").lower()
    found = []
    for vc in KNOWN_VCS:
        key = vc.strip()
        if not key:
            continue
        if key in t and key not in found:
            found.append(key)
    for acc in ACCELERATORS:
        if acc in t and acc not in found:
            found.append(acc)
    return found


def detect_accelerator(text: str, tags: list[str] | None = None) -> str | None:
    tags = tags or []
    t = (text or "").lower()
    for acc in ACCELERATORS:
        if acc in t or acc in " ".join(tags).lower():
            return acc
    return None


def parse_funding_event(text: str) -> dict | None:
    """Parse a funding event from text.

    Returns dict with keys: round (stage), amount_m (float|None),
    investors (list[str]), accelerator (str|None), found (bool).
    """
    t = normalize_text(text)
    lower = t.lower()
    keyword_hit = any(k in lower for k in [
        "raised", "raise", "funding", "seed", "series a", "series b",
        "series c", "pre-seed", "backed", "secured", "lands",
    ])
    if not keyword_hit:
        return None

    stage = UNKNOWN
    round_text = ""
    detected = detect_round(t)
    if detected:
        stage, round_text = detected

    amount = parse_amount(t)
    investors = detect_investors(t)
    accelerator = detect_accelerator(t)

    return {
        "round": stage,
        "round_text": round_text,
        "amount_m": amount,
        "investors": investors,
        "accelerator": accelerator,
        "found": True,
    }


def classify_stage(round_stage: str) -> str:
    return round_stage if round_stage in STAGE_LABELS else UNKNOWN


def is_smart_money_round(funding: dict) -> bool:
    return bool(funding.get("investors"))


def funding_momentum(history: list[dict]) -> dict:
    """Analyze funding history for growth signals.

    history: list of {date, round, amount_m, investors}
    Returns: {growth, frequency, stage_progression, latest_amount_m}
    """
    rounds = sorted((r for r in history if r.get("amount_m") is not None),
                    key=lambda r: r.get("date", ""))
    respected = [r for r in history if r.get("round")]

    amounts = [r["amount_m"] for r in rounds]
    growth = 0.0
    if len(amounts) >= 2:
        growth = round((amounts[-1] / amounts[0] - 1) * 100, 1) if amounts[0] else 0.0

    frequency = 0.0
    if len(respected) >= 2:
        dates = [r.get("date") for r in respected if r.get("date")]
        if len(dates) >= 2:
            try:
                d0 = date.fromisoformat(min(dates))
                d1 = date.fromisoformat(max(dates))
                span_days = (d1 - d0).days or 1
                frequency = round(len(respected) / span_days * 365, 1)
            except ValueError:
                frequency = float(len(respected))

    progression = [r.get("round") for r in
                   sorted(respected, key=lambda r: r.get("date", ""))]
    latest_amount = amounts[-1] if amounts else None

    return {
        "growth": growth,
        "frequency": frequency,
        "stage_progression": progression,
        "latest_amount_m": latest_amount,
    }


STAGE_ORDER = [PRE_SEED, SEED, SERIES_A, SERIES_B, SERIES_C, GROWTH, PUBLIC]


def stage_advanced(progression: list[str]) -> bool:
    """True if progression moves forward through stages (e.g. seed -> series a)."""
    if len(progression) < 2:
        return False
    idx = [STAGE_ORDER.index(s) if s in STAGE_ORDER else -1 for s in progression]
    return all(a < b for a, b in zip(idx, idx[1:]) if a >= 0 and b >= 0) and idx[-1] - idx[0] > 0


def format_amount(amount_m: float | None) -> str:
    if amount_m is None:
        return ""
    if amount_m >= 1000:
        return f"${amount_m / 1000:.1f}B"
    val = round(amount_m, 1)
    if val == int(val):
        val = int(val)
    return f"${val}M"