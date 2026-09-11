"""Korea (Asia/Seoul) time helpers.

Every user-visible date/time in the report and email subject must come from
here so UTC timestamps from the GitHub Actions server are never shown.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - fallback for old Pythons
    ZoneInfo = None

from src.config import SCHEDULE_TIMEZONE

_KST_FALLBACK = timezone(timedelta(hours=9))


def now_kst() -> datetime:
    """Current time in Asia/Seoul with a manual +09:00 fallback."""
    if ZoneInfo is not None:
        try:
            return datetime.now(ZoneInfo(SCHEDULE_TIMEZONE))
        except Exception:
            pass
    return datetime.now(_KST_FALLBACK)


def date_kst() -> str:
    """'2026-09-11' in KST."""
    return now_kst().strftime("%Y-%m-%d")


def korean_date_str(dt: datetime | None = None) -> str:
    """'2026년 9월 11일'."""
    dt = dt or now_kst()
    return f"{dt.year}년 {dt.month}월 {dt.day}일"


def korean_datetime_str(dt: datetime | None = None) -> str:
    """'2026년 9월 11일 오전 10:10' (오전/오후, KST)."""
    dt = dt or now_kst()
    ampm = "오전" if dt.hour < 12 else "오후"
    hour = dt.hour % 12
    if hour == 0:
        hour = 12
    return f"{korean_date_str(dt)} {ampm} {hour}:{dt.minute:02d}"


def kst_compact(dt: datetime | None = None) -> str:
    """'2026-09-11 10:10'."""
    dt = dt or now_kst()
    return f"{dt.year:04d}-{dt.month:02d}-{dt.day:02d} {dt.hour:02d}:{dt.minute:02d}"


def today_kst_iso() -> str:
    """'2026-09-11' (ISO date in KST)."""
    return date_kst()