"""Korean apartment transaction collector (국토교통부 실거래 API).

Reads REAL monthly apartment transaction records from the Ministry of Land,
Infrastructure and Transport open API (data.go.kr / RTMSDataSvcAptTrade).
Every price shown is an actually reported deal — no derived or synthetic
numbers.

When REAL_ESTATE_API_KEY is not configured the source is SKIPPED (mirrors
DART); the report then notes the missing key instead of showing fake data.
"""
from __future__ import annotations

import logging
from xml.etree import ElementTree

import requests

from src.collectors.base import BaseCollector
from src.models import Opportunity, Metrics
from src import timeutil


logger = logging.getLogger(__name__)

API_BASE = "https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade"
DATA_URL = "https://www.data.go.kr/data/15057512/openapi.do"

# (이름, 국토교통부 법정동 코드) — 한국 핵심 거래지역.
REGIONS = [
    ("강남구", "11680"),
    ("서초구", "11650"),
    ("송파구", "11710"),
    ("용산구", "11170"),
    ("마포구", "11440"),
    ("영등포구", "11560"),
    ("성동구", "11200"),
    ("노원구", "11350"),
    ("분당구(성남)", "41135"),
    ("해운대구(부산)", "26350"),
    ("수성구(대구)", "27260"),
    ("연수구(인천)", "28185"),
]

MAX_PER_REGION = 6
MAX_TOTAL = 40


def format_amount_manwon(manwon: int) -> str:
    """'215000' -> '21억5,000만 원' (천만 원 미만은 '만 원'만 표기)."""
    manwon = int(manwon)
    if manwon >= 10000:
        eok = manwon // 10000
        rest = manwon % 10000
        if rest == 0:
            return f"{eok}억 원"
        return f"{eok}억{rest:,}만 원"
    return f"{manwon:,}만 원"


def _txt(item, tag: str) -> str:
    el = item.find(tag)
    return (el.text or "").strip() if el is not None else ""


def _int_or_none(raw: str):
    if raw.isdigit():
        return int(raw)
    return None


def _float_or_none(raw: str):
    try:
        return float(raw)
    except ValueError:
        return None


def _parse_trades(xml_text: str) -> list[dict]:
    """Parse a RTMSDataSvcAptTrade response into normalized trade dicts."""
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        return []
    trades: list[dict] = []
    for item in root.findall(".//item"):
        amount_raw = _txt(item, "거래금액").replace(",", "").replace(" ", "")
        if not amount_raw.isdigit():
            continue
        year, month, day = _txt(item, "년"), _txt(item, "월"), _txt(item, "일")
        if not (year.isdigit() and month.isdigit() and day.isdigit()):
            continue
        trades.append({
            "apt": _txt(item, "아파트") or _txt(item, "법정동"),
            "dong": _txt(item, "법정동"),
            "area": _float_or_none(_txt(item, "전용면적")),
            "floor": _int_or_none(_txt(item, "층")),
            "build_year": _int_or_none(_txt(item, "건축년도")),
            "amount_manwon": int(amount_raw),
            "deal_date": f"{int(year):04d}-{int(month):02d}-{int(day):02d}",
        })
    return trades


def _recent_months(n: int) -> list[str]:
    """Current month first (e.g. ['202608', '202607'])."""
    now = timeutil.now_kst()
    months: list[str] = []
    y, m = now.year, now.month
    for _ in range(n):
        months.append(f"{y}{m:02d}")
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return months


class RealEstateCollector(BaseCollector):
    source_name = "real_estate"

    def __init__(self):
        from src.config import REAL_ESTATE_API_KEY
        self.api_key = (REAL_ESTATE_API_KEY or "").strip()
        self.skipped = False

    def collect(self) -> list[Opportunity]:
        if not self.api_key:
            self.skipped = True
            logger.info("[real_estate] REAL_ESTATE_API_KEY 미설정 — SKIPPED")
            return []
        months = _recent_months(2)
        items: list[Opportunity] = []
        for region, code in REGIONS:
            if len(items) >= MAX_TOTAL:
                break
            trades = self._fetch_region_trades(code, months)
            if not trades:
                continue
            # 최근 월별 1건이라도 있는 지역만 추리며, 가장 최근 달의 데이터를
            # 우선 사용하고 해당 월 데이터가 없으면 이전 달로 후퇴한다.
            trades.sort(key=lambda t: t["amount_manwon"], reverse=True)
            for t in trades[:MAX_PER_REGION]:
                if len(items) >= MAX_TOTAL:
                    break
                items.append(self._to_opportunity(region, code, t))
        return items

    def _fetch_region_trades(self, code: str, months: list[str]) -> list[dict]:
        for ym in months:
            trades = self._fetch_region(code, ym)
            if trades:
                return trades
        return []

    def _fetch_region(self, code: str, ym: str) -> list[dict]:
        params = {
            "serviceKey": self.api_key,
            "LAWD_CD": code,
            "DEAL_YMD": ym,
            "numOfRows": "100",
            "pageNo": "1",
        }
        resp = requests.get(API_BASE, params=params, timeout=20, headers={
            "User-Agent": "Mozilla/5.0 (compatible; OpportunityScanner/1.0)",
        })
        if resp.status_code != 200:
            logger.warning(f"[real_estate] {code}/{ym} HTTP {resp.status_code}")
            return []
        return _parse_trades(resp.text)

    @staticmethod
    def _to_opportunity(region: str, code: str, t: dict) -> Opportunity:
        apt = t["apt"]
        amount = format_amount_manwon(t["amount_manwon"])
        parts = [region, apt, f"실거래 {amount}"]
        if t.get("area"):
            parts.append(f"{t['area']:g}㎡")
        if t.get("floor"):
            parts.append(f"{t['floor']}층")
        parts.append(f"({t['deal_date']})")
        return Opportunity(
            name=f"{apt} ({region})",
            url=DATA_URL,
            description=", ".join(parts),
            category="Real Estate",
            source="real_estate",
            official_url=DATA_URL,
            metrics=Metrics(),
            tags=["korea", "real_estate", "부동산", region, code],
            source_ids=[f"real_estate:{code}:{apt}:{t['deal_date']}"],
            real_estate={
                "region": region,
                "region_code": code,
                "apt": apt,
                "dong": t.get("dong"),
                "area": t.get("area"),
                "floor": t.get("floor"),
                "build_year": t.get("build_year"),
                "amount_manwon": t["amount_manwon"],
                "deal_date": t["deal_date"],
            },
        )