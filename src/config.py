from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
REPORTS_DIR = BASE_DIR / "reports"

AI_ENABLED = os.environ.get("AI_ENABLED", "false").lower() == "true"
AI_API_KEY = os.environ.get("AI_API_KEY", "")
AI_MODEL = os.environ.get("AI_MODEL", "gpt-4o-mini")
AI_BASE_URL = os.environ.get("AI_BASE_URL", "")

SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
EMAIL_TO = os.environ.get("EMAIL_TO", "")

FRED_API_KEY = os.environ.get("FRED_API_KEY", "")

HN_MIN_POINTS = int(os.environ.get("HN_MIN_POINTS", "50"))
HN_HOURS_BACK = int(os.environ.get("HN_HOURS_BACK", "48"))
TOP_N = int(os.environ.get("TOP_N", "5"))
STARTUP_VENTURE_N = int(os.environ.get("STARTUP_VENTURE_N", "12"))
PUBLIC_MARKET_N = int(os.environ.get("PUBLIC_MARKET_N", "5"))
TECHNOLOGY_N = int(os.environ.get("TECHNOLOGY_N", "4"))
PRODUCT_N = int(os.environ.get("PRODUCT_N", "2"))
MA_N = int(os.environ.get("MA_N", "2"))
MACRO_N = int(os.environ.get("MACRO_N", "2"))
MAX_REPORT_ITEMS = int(os.environ.get("MAX_REPORT_ITEMS", "30"))
BREAKOUT_N = int(os.environ.get("BREAKOUT_N", "3"))
MAX_CANDIDATES_FOR_AI = int(os.environ.get("MAX_CANDIDATES_FOR_AI", "30"))
BREAKOUT_THRESHOLD = float(os.environ.get("BREAKOUT_THRESHOLD", "20.0"))
