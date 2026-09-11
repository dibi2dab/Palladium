"""Monthly archive CLI (GitHub Actions entry point).

Packs the previous month's working data → publishes a GitHub Release →
verifies the upload → deletes the month's working data from the repo.

Run:  python backups/archive_monthly.py [YYYY-MM]
The caller (workflow) is responsible for committing the deletions.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.monthly import archive_month

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

if __name__ == "__main__":
    month = sys.argv[1] if len(sys.argv) > 1 else None
    result = archive_month(month=month, publish=True, delete=True)
    print("archive_result=" + str(result).replace("'", '"'))
    if not result.get("verified"):
        sys.exit(1)
    sys.exit(0)