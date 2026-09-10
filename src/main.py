from __future__ import annotations

import json
import logging
import os
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("opportunity-scanner")

sys.path.insert(0, str(Path(__file__).parent))

from src.collectors.github import GitHubTrendingCollector
from src.collectors.hackernews import HackerNewsCollector
from src.collectors.producthunt import ProductHuntCollector
from src.processing.normalizer import normalize_opportunity
from src.processing.deduplicator import deduplicate
from src.processing.filter import filter_candidates
from src.ai.analyzer import AIAnalyzer
from src.history.tracker import HistoryTracker
from src.report.email_template import render_email
from src.report.email_sender import send_email, build_subject


TOP_N = 5
MAX_CANDIDATES_FOR_AI = 25


def main():
    logger.info("=== Opportunity Scanner Starting ===")
    warnings: list[str] = []

    # 1. Collect from all sources
    logger.info("--- Phase 1: Data Collection ---")
    collectors = [
        GitHubTrendingCollector(),
        HackerNewsCollector(min_points=50, hours_back=24),
        ProductHuntCollector(),
    ]

    all_items = []
    for collector in collectors:
        items, error = collector.safe_collect()
        if error:
            warnings.append(f"{collector.source_name} collection failed: {error}")
        all_items.extend(items)

    logger.info(f"Total raw items collected: {len(all_items)}")

    if not all_items:
        logger.warning("No items collected. Generating empty report.")
        _send_empty_report(warnings)
        return

    # 2. Normalize
    logger.info("--- Phase 2: Normalization ---")
    normalized = [normalize_opportunity(opp) for opp in all_items]
    logger.info(f"Normalized: {len(normalized)} items")

    # 3. Deduplicate
    logger.info("--- Phase 3: Deduplication ---")
    unique = deduplicate(normalized)
    logger.info(f"Unique items: {len(unique)}")

    # 4. Filter
    logger.info("--- Phase 4: Filtering ---")
    candidates = filter_candidates(unique)
    logger.info(f"Candidates after filtering: {len(candidates)}")

    # 5. Take top candidates for AI analysis
    candidates_for_ai = candidates[:MAX_CANDIDATES_FOR_AI]
    logger.info(f"Sending {len(candidates_for_ai)} candidates to AI analysis")

    # 6. AI Analysis
    logger.info("--- Phase 5: AI Analysis ---")
    analyzer = AIAnalyzer()
    analyzed = analyzer.analyze_batch(candidates_for_ai)
    logger.info(f"AI analysis complete. {len(analyzed)} items scored.")

    # 7. Sort by total score
    analyzed.sort(key=lambda o: o.total_score, reverse=True)

    # 8. History tracking
    logger.info("--- Phase 6: History Tracking ---")
    tracker = HistoryTracker()
    for opp in analyzed:
        tracker.record_opportunity(opp)
    tracker.save()

    # 9. Get breakouts and watchlist
    breakouts = tracker.get_breakouts(threshold_percent=50.0)
    watchlist = tracker.get_watchlist()

    # 10. Market signals (basic category aggregation)
    market_signals = _compute_market_signals(analyzed)

    # 11. Generate report
    logger.info("--- Phase 7: Report Generation ---")
    top_opps = analyzed[:TOP_N]
    html = render_email(
        top_opportunities=top_opps,
        breakouts=breakouts[:5],
        watchlist=watchlist[:5],
        warnings=warnings,
        market_signals=market_signals,
    )

    # 12. Send email
    logger.info("--- Phase 8: Email Sending ---")
    subject = build_subject(len(top_opps))
    send_email(html, subject)

    # 13. Save raw data
    _save_raw_data(analyzed)

    logger.info("=== Opportunity Scanner Complete ===")


def _compute_market_signals(opps: list) -> dict[str, str]:
    category_scores: dict[str, list[int]] = {}
    for opp in opps:
        cat = opp.category
        if cat not in category_scores:
            category_scores[cat] = []
        category_scores[cat].append(opp.total_score)

    signals: dict[str, str] = {}
    for cat, scores in category_scores.items():
        avg = sum(scores) / len(scores)
        if avg >= 70:
            signals[cat] = "up"
        elif avg >= 50:
            signals[cat] = "flat"
        else:
            signals[cat] = "down"

    signals = dict(sorted(signals.items(), key=lambda x: x[1] != "up"))
    return signals


def _save_raw_data(opps: list):
    data_dir = Path(__file__).parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()

    raw_path = data_dir / f"raw_{today}.json"
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump([opp.to_dict() for opp in opps], f, ensure_ascii=False, indent=2)
    logger.info(f"Raw data saved: {raw_path}")


def _send_empty_report(warnings: list[str]):
    html = render_email(
        top_opportunities=[],
        breakouts=[],
        watchlist=[],
        warnings=warnings or ["No data collected from any source today."],
    )
    subject = f"Opportunity Scanner | {date.today().isoformat()} | No Opportunities"
    send_email(html, subject)


if __name__ == "__main__":
    main()
