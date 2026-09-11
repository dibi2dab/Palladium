"""Entity Type / Event Type classification.

Entity = what the subject IS (company, product, project, person, ...).
Event  = what HAPPENED to it (funding, launch, acquisition, ...).

These are strictly separated: a product name never becomes a Startup,
and a funding signal is only produced by real funding events.
"""
from __future__ import annotations

import re

from src.intelligence.funding import BIG_TECH, KNOWN_VCS

# ---------------------------------------------------------------------------
# Entity types
# ---------------------------------------------------------------------------
STARTUP = "STARTUP"
PRIVATE_COMPANY = "PRIVATE_COMPANY"
PUBLIC_COMPANY = "PUBLIC_COMPANY"
PRODUCT = "PRODUCT"
OPEN_SOURCE_PROJECT = "OPEN_SOURCE_PROJECT"
ORGANIZATION = "ORGANIZATION"
PERSON = "PERSON"
INVESTMENT_VEHICLE = "INVESTMENT_VEHICLE"
OTHER = "OTHER"

ENTITY_TYPE_LABELS = {
    STARTUP: "스타트업",
    PRIVATE_COMPANY: "비상장 기업",
    PUBLIC_COMPANY: "상장 기업",
    PRODUCT: "제품",
    OPEN_SOURCE_PROJECT: "오픈소스 프로젝트",
    ORGANIZATION: "조직",
    PERSON: "개인",
    INVESTMENT_VEHICLE: "투자 기구",
    OTHER: "기타",
}

# ---------------------------------------------------------------------------
# Event types
# ---------------------------------------------------------------------------
FUNDING = "FUNDING"
PRODUCT_LAUNCH = "PRODUCT_LAUNCH"
ACQUISITION = "ACQUISITION"
PARTNERSHIP = "PARTNERSHIP"
HIRING = "HIRING"
EARNINGS = "EARNINGS"
CONTRACT = "CONTRACT"
INVESTMENT = "INVESTMENT"
IPO = "IPO"
DEBT_FINANCING = "DEBT_FINANCING"
REGULATORY = "REGULATORY"
RESEARCH = "RESEARCH"
COMMUNITY_GROWTH = "COMMUNITY_GROWTH"
MARKET_EVENT = "MARKET_EVENT"
OTHER_EVENT = "OTHER_EVENT"

EVENT_TYPE_LABELS = {
    FUNDING: "투자 유치",
    PRODUCT_LAUNCH: "제품 출시",
    ACQUISITION: "인수합병",
    PARTNERSHIP: "파트너십",
    HIRING: "채용 확대",
    EARNINGS: "실적 발표",
    CONTRACT: "대형 계약",
    INVESTMENT: "투자",
    IPO: "상장(IPO)",
    DEBT_FINANCING: "부채 조달",
    REGULATORY: "규제 이슈",
    RESEARCH: "연구 발표",
    COMMUNITY_GROWTH: "커뮤니티 성장",
    MARKET_EVENT: "시장 이벤트",
    OTHER_EVENT: "기타",
}

# Allowed event-type set for validation
EVENT_TYPES = set(EVENT_TYPE_LABELS.keys())

PUBLIC_COMPANY_CATEGORIES = {"public company", "market event", "activist", "ipo", "etf", "index", "corporate"}
PRODUCT_CATEGORIES = {"product", "saas", "developer tools", "design", "productivity", "fintech"}
MARKET_CATEGORIES = {"market event", "economy", "macro event"}

# ---------------------------------------------------------------------------
# Korea (한국) entity recognition
#
# IMPORTANT: classification is about WHAT the subject IS — a Korean company,
# market or product — never about which media covered it. An article being
# published by a Korean outlet is NOT sufficient grounds for the korea flag.
# ---------------------------------------------------------------------------
HANGUL_RE = re.compile(r"[가-힣]")
_KOREAN_DOMAIN_SUFFIXES = (".co.kr", ".go.kr", ".or.kr", ".ac.kr", ".kr")
_KR_MARKET_NAMES = ("kospi", "kosdaq", "krx", "코스피", "코스닥")

KOREA_CORPS = [
    "samsung", "hyundai", "kia", "lg energy", "lg electronics", "lg",
    "sk hynix", "sk", "kakao", "naver", "coupang", "posco", "hanwha",
    "doosan", "kt corp", "kt&g", "kb", "shinhan", "hana", "woori",
    "ncsoft", "netmarble", "krafton", "hybe", "celltrion", "cafe24",
    "toss", "naver webtoon", "kakao bank", "kakao pay", "bithumb",
    "upbit", "두나무", "lf", "대한항공",
]

def is_korean_entity(
    name: str = "",
    url: str = "",
    tags: list[str] | None = None,
    category: str = "",
    ticker: str | None = None,
) -> bool:
    """True when the *subject itself* is Korean (company/market/product).

    Uses only subject-level evidence: 한글 표기, .kr domain, KOSPI/KOSDAQ/KRX
    naming, known Korean group names, or an explicit korea/kr tag set by a
    Korea-focused collector on the SUBJECT (not on the media outlet).
    """
    name = name or ""
    url = url or ""
    tags = [t.lower() for t in (tags or [])]
    category = (category or "").lower()

    if HANGUL_RE.search(name):
        return True
    if name and _KR_MARKET_NAMES and any(k in name.lower() for k in _KR_MARKET_NAMES):
        return True

    try:
        from urllib.parse import urlparse
        netloc = (urlparse(url).netloc or "").lower().replace("www.", "")
    except Exception:
        netloc = ""
    if netloc.endswith(_KOREAN_DOMAIN_SUFFIXES):
        return True

    if any(t in ("korea", "korean", "kr", "한국", "국내") for t in tags):
        return True
    if "korean" in category or "한국" in category:
        return True

    if ticker and ticker.isdigit() and len(ticker) == 6:
        return True  # KRX 6-digit stock code

    name_l = name.lower()
    for corp in KOREA_CORPS:
        # Word-boundary match: short codes like "sk"/"lg"/"kb" must not match
        # inside English words ("Mu-sk", "ba-ck-bone").
        if re.search(r"\b" + re.escape(corp) + r"\b", name_l):
            return True
    return False

_UNVEIL_RE = re.compile(
    r"^(.{3,60}?)\s+(unveils|launches|introduces|debuts|releases)\s+(.{3,})$",
    re.IGNORECASE,
)
_FUNDING_NAME_RE = re.compile(
    r"^(?:(?:[a-z&]+\s){0,4})?"
    r"([A-Z][A-Za-z0-9&.'\-]*(?:\s+[A-Z][A-Za-z0-9&.'\-]+){0,3}?)"
    r"\s+(raises?|raised$|secures?|secured|lands?|scores?|banks?|closes?|nabs?|pockets|scrubs?|cancel[ls]?ed?)\b",
    re.IGNORECASE,
)
_ACQ_NAME_RE = re.compile(
    r"^(.{3,60}?)\s+(to acquire|acquires|agrees to buy|agrees to acquire|buys|to take over)\b",
    re.IGNORECASE,
)

_NON_PRODUCT_REST = re.compile(r"^(?:\$|.*?\b(funding|fund)\b|.*?\b(series|seed)\b)", re.IGNORECASE)


def extract_entity_name(title: str) -> str:
    """Extract a company/product name from a news headline."""
    t = (title or "").strip()
    if not t:
        return ""
    # "X unveils/launches Y" -> the product Y is the subject
    m = _UNVEIL_RE.match(t)
    if m and not _NON_PRODUCT_REST.match(m.group(3)):
        return m.group(3).strip().strip("\"'.,")
    m = _FUNDING_NAME_RE.match(t)
    if m:
        return m.group(1).strip().strip("\"'.,")
    m = _ACQ_NAME_RE.match(t)
    if m:
        return m.group(1).strip().strip("\"'.,")
    return t[:60].strip()


def extract_parent_company(title: str) -> str | None:
    """Return parent company when a headline is '<Parent> unveils <Product>'."""
    t = (title or "").strip()
    m = _UNVEIL_RE.match(t)
    if not m:
        return None
    if _NON_PRODUCT_REST.match(m.group(3)):
        return None
    parent = m.group(1).strip()
    if parent.lower().startswith(("the ", "a ", "an ")):
        return parent
    return parent


def classify_entity_type(
    name: str,
    url: str = "",
    category: str = "",
    tags: list[str] | None = None,
    source: str = "",
    ticker: str | None = None,
    description: str = "",
) -> str:
    tags = [t.lower() for t in (tags or [])]
    cat = (category or "").lower()
    name_l = (name or "").lower()
    desc_l = (description or "").lower()

    if url and "github.com" in url.lower():
        return OPEN_SOURCE_PROJECT
    if "github" in tags or "open source" in tags:
        return OPEN_SOURCE_PROJECT

    if ticker:
        return PUBLIC_COMPANY
    if name_l.strip() in [b.strip() for b in BIG_TECH]:
        return PUBLIC_COMPANY

    # Market/treasury/economy subjects are not companies.
    if re.search(r"\b(rating|treasury|bond|yield|index)\b", name_l):
        return OTHER
    if cat in MARKET_CATEGORIES or "market" in tags or "economy" in tags:
        return OTHER

    if cat in PUBLIC_COMPANY_CATEGORIES:
        return PUBLIC_COMPANY

    if cat in PRODUCT_CATEGORIES or "producthunt" in tags or "kickstarter" in tags:
        return PRODUCT

    if cat in ("funding", "venture", "startup", "private company", "emerging company", "investment"):
        return STARTUP

    if _has_funding_text(name, description):
        return STARTUP

    if name_l.strip() in KNOWN_VCS:
        return INVESTMENT_VEHICLE

    if name and (name_l[0].isupper() or len(name_l) > 2):
        return PRIVATE_COMPANY
    return OTHER


def _has_funding_text(name: str, description: str) -> bool:
    text = f"{name} {description}".lower()
    return any(k in text for k in (
        "raises", "raised", "raising", "funding round", "seed round", "pre-seed",
        "series a", "series b", "series c", "venture round", "backed by",
        "투자 유치", "투자유치", "시리즈", "시드", "투자자", "조달",
    ))


def funded(investors: bool, description: str) -> bool:
    return False


def classify_events(
    name: str,
    description: str,
    category: str = "",
    tags: list[str] | None = None,
    funding_parse: dict | None = None,
) -> list[str]:
    """Return a list of event types for this item (deduped, priority order)."""
    text = f"{name} {description}".lower()
    cat = (category or "").lower()
    tags = [t.lower() for t in (tags or [])]
    events: list[str] = []

    if funding_parse and funding_parse.get("found"):
        events.append(FUNDING)

    if re.search(r"\b(acquir\w*|acqu(?:isition|isitions)|merger\w*|takeover\w*|buyout\w*|takes over)\b"
                 r"|(인수|합병|인수합병|피인수|흡수)", text):
        events.append(ACQUISITION)

    if re.search(r"\b(ipo|initial public offering|spac|to go public|to list publicly)\b"
                 r"|(상장|코스피|코스닥)", text):
        events.append(IPO)

    if re.search(r"\b(unveils?|launches?|launched|introduces?|debuts?|releases?|shipped|roll(?:s|ed)? out)\b"
                 r"|(출시|신제품|런칭|발매)", text):
        events.append(PRODUCT_LAUNCH)

    if re.search(r"\b(partner|partnership|collaborat|integrat|alliance)\b"
                 r"|(협력|제휴|운영 협약|파트너십)", text):
        events.append(PARTNERSHIP)

    if re.search(r"\b(hir(?:ing|es|ed)?|job open(?:ing|ings)|headcount|recruit|team grow)\b"
                 r"|(채용)", text):
        events.append(HIRING)

    if re.search(r"\b(earnings|quarterly results|quarterly report|revenue report|annual results)\b"
                 r"|(실적|매출|영업이익)", text):
        events.append(EARNINGS)

    if re.search(r"\b(d^(-)?signed|awarded|won a deal|contract(?:s)? won|large (?:order|contract))\b", text):
        pass  # conservative: only CONTRACT below with explicit words
    if re.search(r"\b(signs? (?:a )?(?:major |multi-year |large )?contract|\bwon\b.?(?:a )?(?:contract|deal)|awarded (?:a )?contract)\b"
                 r"|(수주|공급계약|공급 계약|수주 계약)", text):
        events.append(CONTRACT)

    if re.search(r"\b(regulatory|approval|approved|fda|antitrust|lawsuit|sued|attorney general)\b"
                 r"|(규제|법안|승인|허가)", text):
        events.append(REGULATORY)

    if re.search(r"\b(research|paper|preprint|benchmark|whitepaper|study)\b"
                 r"|(연구|보고서)", text):
        events.append(RESEARCH)

    if re.search(r"\b(subscribers?|user growth|community grow|milestone users)\b"
                 r"|(사용자|이용자|가입자)", text):
        events.append(COMMUNITY_GROWTH)

    if re.search(r"\b(treasury|yields?|bond market|stock market|stock index|fed|federal reserve|inflation|cpi|oil price|utilities)\b"
                 r"|(증시|주가|자사주|배당|거래량)", text):
        events.append(MARKET_EVENT)

    if not events:
        events.append(OTHER_EVENT)

    return list(dict.fromkeys(events))


# ---------------------------------------------------------------------------
# Macro relevance (used by the scorer so headwinds/tailwinds are not applied
# uniformly to every entity).
# ---------------------------------------------------------------------------
_MACRO_RELEVANCE = {
    "rate_hike": {
        "keywords": ["fintech", "finance", "bank", "mortgage", "real estate",
                     "housing", "property", "credit", "crypto", "consumer"],
        "weight": 2,
    },
    "rate_cut": {
        "keywords": ["fintech", "finance", "bank", "mortgage", "real estate",
                     "housing", "property", "credit", "crypto", "consumer",
                     "growth", "startup"],
        "weight": 2,
    },
    "cpi_high": {
        "keywords": ["consumer", "retail", "food", "grocery", "energy", "import"],
        "weight": 2,
    },
    "cpi_low": {
        "keywords": ["consumer", "retail", "food", "grocery"],
        "weight": 1,
    },
    "gdp_growth": {"keywords": [], "weight": 1},
    "gdp_decline": {"keywords": [], "weight": 1},
    "employment_strong": {"keywords": [], "weight": 1},
    "employment_weak": {"keywords": [], "weight": 1},
    "oil_price_up": {
        "keywords": ["energy", "oil", "gas", "transport", "airline", "shipping",
                     "logistics", "manufacturing"],
        "weight": 2,
    },
    "oil_price_down": {
        "keywords": ["energy", "oil", "gas"],
        "weight": 1,
    },
}


def macro_relevance_score(macro_type: str, entity_text: str) -> int:
    """0 = no relevance. Higher = strong relevance to the entity."""
    spec = _MACRO_RELEVANCE.get(macro_type)
    if not spec:
        return 0
    t = entity_text.lower()
    hits = sum(1 for kw in spec["keywords"] if kw in t)
    if not spec["keywords"]:
        return 1  # broad macro (GDP etc.) has weak baseline relevance
    return min(spec["weight"] * hits, spec["weight"] * 2)