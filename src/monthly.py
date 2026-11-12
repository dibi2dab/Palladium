"""Palladium monthly archive system (§47–52).

Every month the previous month's working data is bundled into a zip,
published as a GitHub Release asset, and ONLY deleted from the repository
after the upload has been verified.

Guaranteed order:

    Pack -> Publish -> Verify Upload -> (delete only if verified)

Never:  Delete -> Archive
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
import zipfile
from datetime import datetime
from pathlib import Path

from src import timeutil
from src.config import DATA_DIR, REPORTS_DIR, REPO_URL, REPO_BRANCH
from src.report.email_sender import send_email

logger = logging.getLogger("palladium.archive")

ARCHIVE_PREFIX = "palladium-"
ARCHIVES_DIR = Path(__file__).parent.parent / "archives"
METADATA_NAME = "metadata/archive.json"

# Current analysis state files bundled into every monthly archive so the
# opportunity/signal history survives the in-repo cleanup (§53).
STATE_FILES = ["entities.json", "signals.json", "history.json.gz", "meta.json"]


def previous_month_kst(now=None) -> str:
    dt = now or timeutil.now_kst()
    month = dt.month - 1
    year = dt.year
    if month == 0:
        month = 12
        year -= 1
    return f"{year:04d}-{month:02d}"


def _gh_repo_from_url(url: str) -> str:
    repo = (url or "").rstrip("/").split("github.com/")[-1].removesuffix(".git")
    return repo


def pack_month(month: str, data_dir: Path = DATA_DIR,
               reports_dir: Path = REPORTS_DIR,
               archive_dir: Path | None = None) -> Path:
    """Bundle reports/<month>-*/ + data/raw_<month>-*.json and a state snapshot
    into archives/palladium-<month>.zip. Returns the zip path.

    Daily reports live in per-day folders (reports/YYYY-MM-DD), so a month is
    matched by the ``<month>-*`` prefix rather than a single ``<month>`` dir.
    """
    report_dirs = sorted(p for p in reports_dir.glob(f"{month}-*") if p.is_dir())
    raw_files = sorted(data_dir.glob(f"raw_{month}*.json"))
    if not report_dirs and not raw_files:
        raise FileNotFoundError(f"No working data found for archive month {month}")

    out = (archive_dir or ARCHIVES_DIR) / f"{ARCHIVE_PREFIX}{month}.zip"
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()

    manifest: list[str] = []

    def _add(path: Path, rel: Path):
        z.write(path, str(rel).replace("\\", "/"))
        manifest.append(str(rel).replace("\\", "/"))

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for report_dir in report_dirs:
            for p in sorted(r for r in report_dir.rglob("*") if r.is_file()):
                _add(p, p.relative_to(reports_dir.parent))
        for raw in raw_files:
            _add(raw, raw.relative_to(data_dir.parent))
        # Snapshot of the current analysis state (exclude raw, keep the rest).
        for name in STATE_FILES:
            sp = data_dir / name
            if sp.is_file():
                _add(sp, Path("state") / name)

        z.writestr(METADATA_NAME, json.dumps({
            "project": "Palladium",
            "month": month,
            "created_at": timeutil.kst_compact(),
            "repo_url": REPO_URL,
            "branch": REPO_BRANCH,
            "entries": sorted(set(manifest)),
        }, ensure_ascii=False, indent=2))

    logger.info("Archive packed: %s (%s entries)", out, len(manifest))
    return out


def _run_gh(args: list[str]) -> tuple[int, str]:
    try:
        r = subprocess.run(["gh"] + args, capture_output=True, text=True,
                           timeout=180)
        return r.returncode, (r.stdout or "") + ("\n" + r.stderr if r.stderr else "")
    except FileNotFoundError:
        return 127, "gh CLI not found"
    except Exception as e:  # subprocess timeout etc.
        return 1, str(e)


def publish_release(month: str, asset: Path,
                    repo: str | None = None) -> str | None:
    """Create a GitHub Release `archive-<month>` and upload the zip.

    Returns the release URL when creation AND asset upload are verified,
    None otherwise.
    """
    repo = repo or _gh_repo_from_url(REPO_URL)
    tag = f"archive-{month}"
    code, msg = _run_gh([
        "release", "create", tag, str(asset),
        "--repo", repo,
        "--title", f"Palladium Monthly Archive {month}",
        "--notes", f"Monthly working data archive for {month}. See metadata/archive.json.",
    ])
    if code != 0:
        logger.error("gh release create failed (%s): %s", code, msg.strip())
        return None

    # Verify the upload (asset must actually exist on the release).
    code, msg = _run_gh(["release", "view", tag, "--repo", repo,
                         "--json", "assetCount", "--jq", ".assetCount"])
    if code == 0 and msg.strip().isdigit() and int(msg.strip()) >= 1:
        return f"https://github.com/{repo}/releases/tag/{tag}"
    logger.error("Release upload could not be verified: %s", msg.strip())
    return None


def delete_month_working_data(month: str, data_dir: Path = DATA_DIR,
                              reports_dir: Path = REPORTS_DIR) -> int:
    """Remove the month's working data from the repo. Returns removed count."""
    removed = 0
    for report_dir in sorted(reports_dir.glob(f"{month}-*")):
        if report_dir.is_dir():
            shutil.rmtree(report_dir)
            removed += 1
    for raw in data_dir.glob(f"raw_{month}*.json"):
        raw.unlink(missing_ok=True)
        removed += 1
    if removed:
        logger.info("Deleted %s working item(s) for %s", removed, month)
    return removed


def archive_month(month: str | None = None,
                  publish: bool = True,
                  delete: bool = False,
                  publisher=None,
                  data_dir: Path = DATA_DIR,
                  reports_dir: Path = REPORTS_DIR,
                  archive_dir: Path | None = None,
                  _now=None) -> dict:
    """Run the monthly archive pipeline.

    Returns {month, archive, release_url, verified, deleted, emails}.

    Deletion NEVER happens unless publish succeeded and the release was
    verified. With publish=False the archive is only packed locally.
    """
    month = month or previous_month_kst(_now)
    result: dict = {
        "month": month,
        "archive": None,
        "release_url": None,
        "verified": False,
        "deleted": 0,
        "email_sent": False,
    }

    try:
        asset = pack_month(month, data_dir, reports_dir, archive_dir)
    except FileNotFoundError as e:
        logger.warning("Archive skipped: %s", e)
        return result
    result["archive"] = str(asset)

    if not publish:
        logger.info("publish=False — archive kept locally, nothing deleted.")
        return result

    pub = publisher or publish_release
    try:
        url = pub(month, asset)
    except Exception as e:
        logger.error("publisher raised: %s", e)
        url = None

    if not url:
        logger.error("Upload not verified — working data was NOT deleted.")
        return result

    result["release_url"] = url
    result["verified"] = True

    if delete:
        result["deleted"] = delete_month_working_data(month, data_dir, reports_dir)
        try:
            result["email_sent"] = send_archive_email(month, url)
        except Exception as e:
            logger.error("Archive email failed: %s", e)

    return result


def send_archive_email(month: str, release_url: str) -> bool:
    subject = f"Palladium Monthly Archive | {month}"
    body = (f"<h1>Palladium Monthly Archive</h1><p>{month}</p>"
            f"<p>Monthly working data has been archived.</p>"
            f"<p>Download: <a href='{release_url}'>{release_url}</a></p>"
            f"<p>Period: {month}-01 ~ {month}-31 (KST)</p>"
            f"<p>Contents: reports, raw signals, entity/score history, metadata.</p>")
    return send_email(body, subject)