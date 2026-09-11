from __future__ import annotations

import logging
import re
import time
from xml.etree import ElementTree

import requests

from src.collectors.base import BaseCollector
from src.models import Opportunity, Metrics


logger = logging.getLogger(__name__)

HANGUL_RE = re.compile(r"[가-힣]")

# Korean focus queries (Google News RSS, hl=ko&gl=KR — free, no login).
KOREA_QUERIES = [
    "스타트업 투자 유치",
    "스타트업 시리즈 투자",
    "기업 상장 공시",
    "수주 공급계약",
    "자사주 매입 배당",
    "실적 발표 매출",
    "기업 해외 진출",
    "기업 M&A 인수",
    "신제품 출시",
]

KOREA_CATEGORY_KEYWORDS = {
    "Funding": ["투자 유치", "투자유치", "시리즈", "시드", "조달", "펀딩", "투자자", "유상증자"],
    "M&A": ["인수", "합병", "피인수", "흡수", "M&A"],
    "IPO": ["상장", "IPO", "코스피", "코스닥", "상장 예비"],
    "Product": ["출시", "신제품", "런칭", "발매"],
    "Market Event": ["자사주", "배당", "실적", "영업이익", "거래량", "주가", "증시"],
    "Corporate": ["수주", "공급계약", "계약", "국책", "정부"],
    "Technology": ["AI", "인공지능", "반도체", "배터리", "로봇", "플랫폼", "기술"],
}


def extract_korean_company(title: str) -> str:
    """Extract a company/subject name from a Korean headline.

    Most Korean financial headlines are '<회사명>, <내용>'. We take the part
    before the first comma/colon and fall back to the full title when that
    part is empty or does not contain Korean script.
    """
    t = (title or "").strip()
    m = re.split(r"[,，:：]", t, maxsplit=1)
    head = m[0].strip()
    head = re.sub(r"[\"'\"'「」『』\[\]()（）]+$", "", head).strip()
    if head and HANGUL_RE.search(head) and len(head) <= 14:
        return head
    return t[:60].strip()


def guess_korean_category(title: str, description: str) -> str:
    c = f"{title} {description}"
    for cat, kws in KOREA_CATEGORY_KEYWORDS.items():
        if any(k in c for k in kws):
            return cat
    return "Startup" if HANGUL_RE.search(c) else "News"


class KoreaNewsCollector(BaseCollector):
    """Korean startup/market/tech signals from Google News (Korean).

    Items are classified as korea via subject-level tags; being published by
    Korean media alone is never enough to be treated as a Korean opportunity.
    """

    source_name = "korea_news"

    def collect(self) -> list[Opportunity]:
        results: list[Opportunity] = []
        for query in KOREA_QUERIES:
            try:
                results.extend(self._collect_query(query))
            except Exception as e:
                logger.warning(f"[korea_news] query '{query}' failed: {e}")
        return results

    def _collect_query(self, query: str) -> list[Opportunity]:
        results: list[Opportunity] = []
        url = f"https://news.google.com/rss/search?q={query}+when:2d&hl=ko&gl=KR"
        resp = requests.get(url, timeout=15, headers={
            "User-Agent": "Mozilla/5.0 (compatible; OpportunityScanner/1.0)",
        })
        if resp.status_code != 200:
            return results

        root = ElementTree.fromstring(resp.content)
        for item in root.findall(".//item")[:8]:
            title_el = item.find("title")
            link_el = item.find("link")
            if title_el is None:
                continue
            title = (title_el.text or "").strip()
            if not HANGUL_RE.search(title):
                continue
            link = (link_el.text or "").strip() if link_el is not None else ""

            name = extract_korean_company(title)
            desc = title
            category = guess_korean_category(title, desc)

            results.append(Opportunity(
                name=name,
                url=link or f"https://news.google.com/search?q={query}&hl=ko",
                description=desc,
                category=category,
                source="korea_news:google_news",
                official_url=link,
                metrics=Metrics(news_mentions=1),
                tags=["korea", "korean", "google_news", category.lower().replace(" ", "_")],
                source_ids=[f"korea_news:{title[:40]}"],
            ))
        return results


class DartCollector(BaseCollector):
    """Korean corporate disclosures via the free DART(FSS) open API.

    Requires DART_API_KEY (free registration at dart.fss.or.kr). When the key
    is missing the collector reports an error instead of failing the scan, so
    the pipeline still runs with the other sources.
    """

    source_name = "dart"

    BASE = "https://opendart.fss.or.kr/api"

    INTEREST_KEYWORDS = [
        "유상증자", "자사주", "배당", "실적", "수주", "상장", "합병", "인수",
        "공급계약", "대규모 투자", "분할", "사업보고서", "반기보고서", "분기보고서",
    ]

    def __init__(self):
        from src.config import DART_API_KEY
        self.api_key = DART_API_KEY

    def collect(self) -> list[Opportunity]:
        if not self.api_key:
            logger.info("[dart] DART_API_KEY not set; skipping DART source")
            return []
        results: list[Opportunity] = []
        from src.timeutil import date_kst
        end = date_kst()
        params = {
            "crtfc_key": self.api_key,
            "bgn_de": _shift_date(end, -1),
            "end_de": end,
            "page_no": 1,
            "page_count": 20,
        }
        try:
            resp = requests.get(f"{self.BASE}/list.json", params=params, timeout=20,
                                headers={"User-Agent": "OpportunityScanner/1.0"})
            if resp.status_code != 200:
                logger.warning(f"[dart] list.json returned {resp.status_code}")
                return []
            data = resp.json()
            if data.get("status") != "000":
                logger.warning(f"[dart] API error: {data.get('message')}")
                return []
        except Exception as e:
            logger.warning(f"[dart] list.json failed: {e}")
            return []

        for item in data.get("list", []):
            report_nm = (item.get("report_nm") or "").strip()
            if not report_nm or not any(k in report_nm for k in self.INTEREST_KEYWORDS):
                continue
            corp_name = self._corp_name(item.get("corp_code", ""))
            if not corp_name:
                continue
            rcept_dt = item.get("rcept_dt") or ""
            link = f"http://dart.fss.or.kr/dsaf001/main.do?rcpNo={item.get('rcept_no', '')}"
            results.append(Opportunity(
                name=corp_name,
                url=link,
                description=f"{corp_name} — {report_nm} (DART 공시 {rcept_dt})",
                category=guess_korean_category(report_nm, corp_name),
                source="dart:fss",
                official_url=link,
                metrics=Metrics(news_mentions=1),
                tags=["korea", "dart", "공시", "disclosure"],
                source_ids=[f"dart:{item.get('rcept_no', '')}"],
            ))
        return results

    def _corp_name(self, corp_code: str) -> str:
        """Resolve corp_code → company name via the DART company endpoint."""
        if not corp_code:
            return ""
        try:
            resp = requests.get(
                f"{self.BASE}/company.json",
                params={"crtfc_key": self.api_key, "corp_code": corp_code},
                timeout=15, headers={"User-Agent": "OpportunityScanner/1.0"},
            )
            time.sleep(1.2)  # free tier rate limit (1 req/sec)
            data = resp.json()
            if data.get("status") == "000":
                name = data.get("corp_name") or ""
                return name.strip()
        except Exception as e:
            logger.warning(f"[dart] company.json failed for {corp_code}: {e}")
        return ""


def _shift_date(iso_date: str, days: int) -> str:
    from datetime import datetime, timedelta
    dt = datetime.strptime(iso_date, "%Y-%m-%d") + timedelta(days=days)
    return dt.strftime("%Y%m%d")