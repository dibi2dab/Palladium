"""Palladium YAML configuration loader.

Loads config/*.yml as the single source of truth for thresholds, source
reliability tiers, category focus and scoring chains. Every accessor falls
back to a built-in default so the pipeline always runs even without YAML.

GraphQL rule: NO AI — the pipeline is rule / threshold / statistics only.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    import yaml  # pyyaml
except ImportError:  # pragma: no cover - optional dependency
    yaml = None

_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


def _load(name: str, default: dict) -> dict:
    if yaml is None:
        return default
    path = _CONFIG_DIR / f"{name}.yml"
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        if not isinstance(data, dict):
            return default
        return {**default, **data}
    except Exception:
        return default


# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

_DEFAULT_THRESHOLDS: dict[str, Any] = {
    "score_bands": {"priority": 80, "emerging": 70, "watch": 50,
                    "top_min_score": 70, "include_min_score": 50},
    "section_caps": {"top_n": 5, "startup_venture_n": 12, "public_market_n": 5,
                     "technology_n": 4, "product_n": 3, "ma_n": 2, "macro_n": 3,
                     "korea_startup_n": 10, "korea_public_n": 7,
                     "korea_tech_n": 5, "max_report_items": 50},
    "breakout": {"threshold": 20.0},
    "convergence": {"min_distinct_signals": 3, "min_strong_signals": 2,
                    "strong_categories": ["funding", "funding_round", "hiring",
                                          "github", "product_launch",
                                          "community", "customer"]},
    "trajectory": {"min_entries": 3, "window": 5,
                   "accel_delta": 10, "decay_delta": -10},
}

_CONF_THRESHOLDS = _load("thresholds", _DEFAULT_THRESHOLDS)


def score_bands() -> dict:
    return _CONF_THRESHOLDS.get("score_bands", {})


def section_caps() -> dict:
    return _CONF_THRESHOLDS.get("section_caps", {})


def breakout_threshold() -> float:
    return float(_CONF_THRESHOLDS.get("breakout", {}).get("threshold", 20.0))


def convergence_rules() -> dict:
    return _CONF_THRESHOLDS.get("convergence", {})


def trajectory_rules() -> dict:
    return _CONF_THRESHOLDS.get("trajectory", {})


# ---------------------------------------------------------------------------
# Sources (evidence quality tiers)
# ---------------------------------------------------------------------------

_DEFAULT_SOURCES: dict[str, Any] = {
    "reliability": {
        "VERY_HIGH": ["dart", "fss", "sec_edgar", "fred", "gov"],
        "HIGH": ["reuters", "bloomberg", "wsj", "financial times", "ft",
                 "ycombinator", "github", "official"],
        "MEDIUM": ["techcrunch", "google_news", "news", "producthunt",
                   "medium", "hackernoon", "venturebeat", "arstechnica"],
        "LOW": ["reddit", "twitter", "unverified", "x"],
    },
    "official_domain_suffixes": [".go.kr", ".or.kr", ".ac.kr", ".kr",
                                 ".gov", ".org"],
}

_CONF_SOURCES = _load("sources", _DEFAULT_SOURCES)


def source_reliability() -> dict:
    return _CONF_SOURCES.get("reliability", {})


def official_domain_suffixes() -> list[str]:
    return _CONF_SOURCES.get("official_domain_suffixes", [])


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------

_DEFAULT_CATEGORIES: dict[str, Any] = {
    "report_domains": {},
    "korea_focus": {},
}

_CONF_CATEGORIES = _load("categories", _DEFAULT_CATEGORIES)


def report_domains() -> dict:
    return _CONF_CATEGORIES.get("report_domains", {})


# ---------------------------------------------------------------------------
# Scoring (second-order chains)
# ---------------------------------------------------------------------------

_DEFAULT_SCORING: dict[str, Any] = {
    "second_order_chains": {
        "ai": ["GPU·가속기 수요 (데이터센터)", "AI 애플리케이션·에이전트 부가가치"],
        "gpu": ["데이터센터·전력 인프라", "냉각·전력 솔루션", "커스텀 반도체·패키징"],
        "semiconductor": ["반도체 장비·소재", "패키징·테스트", "파워 반도체·전력 관리"],
        "battery": ["전기차·이차전지 체인", "ESS·그리드 저장", "배터리 원자재·리사이클링"],
        "ev": ["충전 인프라", "배터리·전장 부품", "배터리 원자재"],
        "robotics": ["센서·추론 부품", "자율주행·물류 자동화", "로봇 소프트웨어"],
        "data": ["클라우드 인프라", "보안·규제 대응", "데이터 파이프라인"],
        "cloud": ["멀티클라우드 관리·비용", "보안·망 분리", "데이터 파이프라인"],
    },
    "macro_second_order": {
        "rate_cut": ["금리 민감 업종(부동산·성장주) 자금 조달 환경 개선"],
        "rate_hike": ["채권 수익률 상승·예금 금리 경쟁"],
        "cpi_high": ["소비재 가격 민감도·원자재 수급"],
        "cpi_low": ["소비재 마진 개선"],
        "gdp_growth": ["경기 민감 산업 수요 증가"],
        "gdp_decline": ["방어주·현금 흐름 중심 전략"],
        "oil_price_up": ["항공·운송 비용 압력 → 에너지 대체재"],
        "oil_price_down": ["에너지 업스트림 마진 압박"],
    },
}

_CONF_SCORING = _load("scoring", _DEFAULT_SCORING)


def second_order_chains() -> dict:
    return _CONF_SCORING.get("second_order_chains", {})


def macro_second_order() -> dict:
    return _CONF_SCORING.get("macro_second_order", {})