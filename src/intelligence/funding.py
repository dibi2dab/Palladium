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

STAGE_LABELS_KO = {
    PRE_SEED: "시드 전 단계(Pre-Seed)",
    SEED: "시드(Seed)",
    SERIES_A: "시리즈 A",
    SERIES_B: "시리즈 B",
    SERIES_C: "시리즈 C",
    GROWTH: "성장 후기",
    PUBLIC: "상장",
    UNKNOWN: "확인 필요",
}

# Round keywords in priority order (word-boundary aware)
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
    ("late stage", GROWTH),
    ("late-stage", GROWTH),
    ("ipo", PUBLIC),
    ("spac", PUBLIC),
]

_WHITESPACE = re.compile(r"\s+")


def _normalize_text(text: str) -> str:
    t = re.sub(r"<[^>]+>", " ", text or "").replace("\xa0", " ")
    return _WHITESPACE.sub(" ", t)


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
    "usv", "union square ventures", "accel partners",
    "peak xv", "greenoaks", "hospitality",
]

ACCELERATORS = [
    "y combinator", "techstars", "500 global", "antler", "500 startups",
    "plug and play", "masschallenge", "alchemist accelerator", "data collective",
]

# Large public companies whose ordinary product news should NOT dominate
BIG_TECH = [
    "apple", "google", "alphabet", "microsoft", "meta", "facebook",
    "amazon", "samsung", "tesla", "openai", "nvidia", "netflix",
    "intel", "ibm", "oracle", "salesforce", "adobe",
    "uber", "airbnb", "twitter", "linkedin", "snap", "palantir",
    "anthropic", "x corp",
]

AMOUNT_RE = re.compile(
    r"\$\s?([0-9][0-9,\.]*)\s?(m|mn|million|k|kilo|b|bn|billion)\b",
    re.IGNORECASE,
)
AMOUNT_EUR_RE = re.compile(
    r"€\s?([0-9][0-9,\.]*)\s?(m|mn|million|k|kilo|b|bn|billion)\b",
    re.IGNORECASE,
)

# Phrases that CONFIRM a real funding event (not stock moves, treasury
# articles, product launches, or general investor opinions).
FUNDING_CONFIRM_RE = [
    re.compile(r"\bpre[- ]?seed\b", re.IGNORECASE),
    re.compile(r"\bseed round\b", re.IGNORECASE),
    re.compile(r"\bventure(?: capital)? round\b", re.IGNORECASE),
    re.compile(r"\bequity financing\b", re.IGNORECASE),
    re.compile(r"\bfunding round\b", re.IGNORECASE),
    re.compile(r"\bseries [a-e]\b", re.IGNORECASE),
    re.compile(r"\brais(?:es|ed|ing)?\b", re.IGNORECASE),
    re.compile(r"\bsecures?\b.{0,80}?(?:financing|funding|round|investment)", re.IGNORECASE),
    re.compile(r"\b(?:lands?|scores?|banks?|nabs?|pockets?)\b.{0,60}?\$", re.IGNORECASE),
    re.compile(r"\bcloses?\b.{0,60}?(?:funding|round|financing|investment)", re.IGNORECASE),
]

EXCLUDE_FUNDING_NAVIGATION = [
    "treasury", "yield", "bond", "stock market", "index", "saver", "deposit",
    "insurance", "mutual fund", "hedge fund manager",
]

WITHDRAWAL_KEYWORDS = [
    "scrubbed", "scrubs", "cancelled", "canceled", "cancels", "withdrawn",
    "withdraws", "abandoned", "walked away", "dropped", "failed to close",
    "terminated", "pulled", "rescinded", "scrapped", "called off",
    "fell through", "walk away", "has been cancelled",
]


def normalize_text(text: str) -> str:
    return _normalize_text(text)


def parse_amount(text: str) -> float | None:
    """Extract a USD amount, normalized to millions (e.g. 3.5 for $3.5M)."""
    t = _normalize_text(text)
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


def parse_amount_currency(text: str) -> tuple[float | None, str]:
    """Return (amount_m, currency_label) for a USD or EUR amount."""
    usd = parse_amount(text)
    if usd is not None:
        return usd, "USD"
    t = _normalize_text(text)
    m = AMOUNT_EUR_RE.search(t)
    if m:
        try:
            val = float(m.group(1).replace(",", ""))
        except ValueError:
            return None, ""
        unit = m.group(2).lower()
        if unit in ("b", "bn", "billion"):
            val *= 1000.0
        elif unit in ("k", "kilo", "thousand"):
            val /= 1000.0
        return round(val, 2), "EUR"
    return None, ""


def detect_round(text: str) -> tuple[str, str] | None:
    """Return (stage, matched_round_text) or None. Word-boundary aware."""
    t = (_normalize_text(text) or "").lower()
    for pattern, stage in ROUND_PATTERNS:
        if pattern in t:
            if pattern == "seed":
                # make sure "seed" isn't part of "pre-seed"/"pre seed"/"seed round"
                if "pre-seed" in t or "pre seed" in t or "seed round" in t:
                    continue
            return stage, pattern
    return None


def detect_withdrawal(text: str) -> bool:
    t = (_normalize_text(text) or "").lower()
    return any(kw in t for kw in WITHDRAWAL_KEYWORDS)


def is_funding_event(text: str) -> bool:
    """Strict funding check. Only true confirmations return True.

    Stock moves, yields, treasury, product launches, acquisitions and
    partnerships without an explicit raise/series/seed pattern are NOT
    treated as funding.
    """
    t = _normalize_text(text)
    lower_t = t.lower()
    if detect_withdrawal(text):
        return True  # a planned/withdrawn round is still a funding event
    if not any(r.search(t) for r in FUNDING_CONFIRM_RE):
        return False
    # If the text is mostly about markets/treasuries, reject.
    excluded_hits = sum(1 for e in EXCLUDE_FUNDING_NAVIGATION if e in lower_t)
    if excluded_hits >= 2:
        return False
    if excluded_hits == 1 and not any(
        r.search(t) for r in FUNDING_CONFIRM_RE[:6]
    ):
        return False
    return True


def detect_round_priority(title: str, description: str | None) -> tuple[str, str | None]:
    """Determine the funding stage with title priority.

    Returns (stage, stage_source) where stage_source is 'title', 'body',
    or None. If title and body disagree, title wins but the caller keeps a
    low confidence marker via stage_source='conflict' combined with the title
    stage.
    """
    title_round = detect_round(title or "")
    body_round = detect_round(description or "") if description else None

    if title_round:
        if body_round and body_round[0] != title_round[0]:
            return title_round
        return title_round
    if body_round:
        return body_round
    return UNKNOWN, None


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


def parse_funding_event(title: str, description: str | None = None) -> dict | None:
    """Parse a funding event from a title plus optional description.

    Returns dict with keys:
      found (bool), status ('confirmed'/'planned'/'withdrawn'),
      round (stage), round_text (str|None), stage_confidence ('high'/'medium'/'low'),
      amount_m (float|None), currency ('USD'/'EUR'/''),
      investors (list), accelerator (str|None), url_hint (str|None).

    'planned' means a planned amount is mentioned without confirmation the
    round closed; 'withdrawn' means the round was cancelled/scrubbed —
    these are NOT positive funding signals.
    """
    desc = description or title
    title_n = _normalize_text(title)
    body_n = _normalize_text(desc)

    combined = f"{title_n} {body_n}"

    status = "confirmed"
    if detect_withdrawal(combined):
        status = "withdrawn"
    elif not is_funding_event(combined):
        return None
    elif _looks_planned(title_n, body_n):
        status = "planned"

    stage, round_text = detect_round_priority(title_n, description or "")

    body_round = detect_round(body_n) if description else None
    if stage != UNKNOWN:
        if body_round and body_round[0] != stage:
            stage_confidence = "low"
        else:
            stage_confidence = "high" if round_text and round_text in title_n else "medium"
    else:
        stage_confidence = "low"

    # Amount: prefer the title, then the body.
    amount_m, currency = parse_amount_currency(title_n)
    if amount_m is None and status != "withdrawn":
        amount_m, currency = parse_amount_currency(body_n)

    investors = detect_investors(combined)
    accelerator = detect_accelerator(combined)

    return {
        "found": True,
        "status": status,
        "round": stage,
        "round_text": round_text,
        "stage_confidence": stage_confidence,
        "amount_m": amount_m,
        "currency": currency,
        "investors": investors,
        "accelerator": accelerator,
        "url_hint": None,
    }


def _looks_planned(title: str, body: str) -> bool:
    """Detect 'plans to raise X' phrasing where the money may not be secured."""
    t = f"{title} {body}".lower()
    return bool(re.search(
        r"\b(plans? (?:to )?raise|expected (?:to )?raise|targets? (?:to )?raise|"
        r"aims? (?:to )?raise|could raise|may raise|negotiating a|in talks for a)\b",
        t,
    ))


def classify_stage(round_stage: str) -> str:
    return round_stage if round_stage in STAGE_LABELS else UNKNOWN


def is_smart_money_round(funding: dict) -> bool:
    return bool(funding.get("investors"))


def funding_momentum(history: list[dict]) -> dict:
    """Analyze funding history for growth signals.

    history: list of {date, round, amount_m, investors, currency}
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
    """True if progression moves forward through stages (seed -> series a)."""
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


def currency_label(currency: str) -> str:
    return {"USD": "달러", "EUR": "유로"}.get(currency, "달러")


def format_amount_kr(amount_m: float | None, currency: str = "USD") -> str:
    """Human-readable Korean amount, e.g. $50M -> '5,000만 달러'."""
    if amount_m is None:
        return ""
    usd = amount_m * 1_000_000.0
    suffix = currency_label(currency)

    abs_usd = abs(usd)
    if abs_usd >= 1e12:
        val = usd / 1e12
        unit = "조"
    elif abs_usd >= 1e8:
        val = usd / 1e8
        unit = "억"
    elif abs_usd >= 1e4:
        val = usd / 1e4
        unit = "만"
    else:
        val = usd
        unit = ""

    if val == int(val):
        num = f"{int(val):,}"
        approx = ""
    elif val * 100 == int(val * 100) and val != int(val):
        num = f"{val:,.2f}".rstrip("0").rstrip(".")
        approx = "약 "
    else:
        num = f"{val:,.2f}".rstrip("0").rstrip(".")
        approx = "약 "

    if not unit:
        return f"{num} {suffix}"
    return f"{approx}{num}{unit} {suffix}"