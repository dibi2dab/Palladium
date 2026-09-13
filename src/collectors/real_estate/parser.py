"""Turn public statistics files into normalized series records.

A series record is a flat dict:
  {"period": "202608", "region": "전국", "item": "아파트 매매가격지수",
   "value": 108.9}

Parsing is deliberately graceful: malformed input never raises — it yields an
empty list so a bad file cannot kill the pipeline.
"""
from __future__ import annotations

import csv
import io
import json
import logging


logger = logging.getLogger(__name__)

PERIOD_ALIASES = ("period", "기간", "시점", "수록시점", "기준월")
REGION_ALIASES = ("region", "지역", "지역명", "시도")
ITEM_ALIASES = ("item", "항목", "지표", "용도")
VALUE_ALIASES = ("value", "값", "수치", "가격", "지수")

_UNSET = object()


def _to_float(raw) -> float | None:
    if raw is None:
        return None
    s = str(raw).replace(",", "").replace("원", "").replace("%", "").strip()
    if not s or s in ("-", "…", "..", ".", "총계", "합계"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _header_index(row: list[str]) -> dict[str, int] | None:
    low = [str(c).strip().lower() for c in row]
    idx: dict[str, int] = {}
    for field, aliases in (
        ("period", PERIOD_ALIASES),
        ("region", REGION_ALIASES),
        ("item", ITEM_ALIASES),
        ("value", VALUE_ALIASES),
    ):
        for a in aliases:
            if a.lower() in low:
                idx[field] = low.index(a.lower())
                break
    if "period" in idx and "value" in idx:
        return idx
    return None


def _parse_period(raw) -> str:
    return str(raw or "").strip()


def _parse_text(text: str, kind: str) -> list[dict]:
    if kind == "csv":
        records: list[dict] = []
        try:
            reader = csv.reader(io.StringIO(text))
            rows = [r for r in reader if r and any(str(c).strip() for c in r)]
        except Exception as exc:  # graceful: bad CSV never raises
            logger.warning("[real_estate] CSV read failed: %s", exc)
            return records
        header = None
        for i, row in enumerate(rows):
            idx = _header_index(row)
            if idx is not None:
                header = (i, idx)
                break
        if header is None:
            return records
        start, idx = header
        for row in rows[start + 1:]:
            if len(row) <= max(idx.values()):
                continue
            value = _to_float(row[idx["value"]])
            if value is None:
                continue
            records.append({
                "period": _parse_period(row[idx["period"]]),
                "region": str(row[idx["region"]]).strip()
                if "region" in idx else "전체",
                "item": str(row[idx["item"]]).strip()
                if "item" in idx else "",
                "value": value,
            })
        return records

    # JSON: a list of dicts, or a mapping whose values contain such a list.
    records = []
    try:
        obj = json.loads(text)
    except ValueError as exc:
        logger.warning("[real_estate] JSON read failed: %s", exc)
        return records
    if isinstance(obj, dict):
        for candidate in obj.values():
            if (isinstance(candidate, list) and candidate
                    and isinstance(candidate[0], dict)):
                obj = candidate
                break
    if not isinstance(obj, list):
        return records
    for row in obj:
        if not isinstance(row, dict):
            continue
        value = _to_float(row.get("value"))
        if value is None:
            continue
        records.append({
            "period": _parse_period(row.get("period")),
            "region": str(row.get("region", "전체")).strip(),
            "item": str(row.get("item", "")).strip(),
            "value": value,
        })
    return records


def parse_source(kind: str, content: bytes, encoding: str = "utf-8") -> list[dict]:
    """Parse CSVs' sample bytes into records for the given kind ('csv'/'json')."""
    if kind not in ("csv", "json"):
        raise RuntimeError(f"unsupported source kind: {kind}")
    body = content.lstrip(b"\xef\xbb\xbf")  # strip UTF-8 BOM if present
    try:
        text = body.decode(encoding or "utf-8", errors="replace")
    except (LookupError, UnicodeError) as exc:
        raise RuntimeError("source is not decodable as %s" % (encoding or "utf-8")) from exc
    return _parse_text(text, kind)