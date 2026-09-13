"""Keyless real-estate market-watch module (공식 공개 통계 파일 기반).

Replaces the old data.go.kr key-based collector. Sources are public CSV/JSON
files only — no API key, token, login, or other secret is ever required.
Series values are recorded as-is; nothing is guessed or extrapolated.
"""
from src.collectors.real_estate.collector import RealEstateCollector

__all__ = ["RealEstateCollector"]