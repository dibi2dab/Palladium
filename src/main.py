from __future__ import annotations

import json
import logging
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("opportunity-scanner")

from src.config import (
    DATA_DIR, REPORTS_DIR, AI_ENABLED, TOP_N, BREAKOUT_N, BREAKOUT_THRESHOLD,
    MAX_CANDIDATES_FOR_AI,
)
from src.storage.json_store import JsonStore
from src.collectors.startups import StartupCollector
from src.collectors.markets import MarketCollector
from src.collectors.economy import EconomyCollector
from src.collectors.products import ProductCollector
from src.collectors.technology import TechnologyCollector
from src.collectors.news import NewsCollector
from src.collectors.reddit import RedditCollector
from src.collectors.funding import FundingCollector
from src.intelligence.entities import EntityManager
from src.intelligence.signals import SignalManager
from src.intelligence.scoring import Scorer, ScoredEntity
from src.intelligence.breakout import BreakoutDetector
from src.intelligence.selection import build_sections, total_count
from src.intelligence.funding import (
    UNKNOWN, STAGE_LABELS, parse_funding_event, detect_round,
    funding_momentum,
)
from src.report.email_template import render_email
from src.report.email_sender import send_email, build_subject


COLLECTOR_MAP = {
    "startups": StartupCollector,
    "funding": FundingCollector,
    "markets": MarketCollector,
    "economy": EconomyCollector,
    "products": ProductCollector,
    "technology": TechnologyCollector,
    "news": NewsCollector,
    "reddit": RedditCollector,
}


def main():
    logger.info("=== Opportunity Scanner Starting ===")
    warnings: list[str] = []

    store = JsonStore()
    entities = EntityManager(store)
    signals = SignalManager(store)
    breakout = BreakoutDetector(store)

    # 1. Collect
    logger.info("--- Phase 1: Data Collection ---")
    all_opportunities = []
    for name, cls in COLLECTOR_MAP.items():
        try:
            collector = cls()
            items, error = collector.safe_collect()
            if error:
                warnings.append(f"{name}: {error}")
                logger.warning(f"[{name}] Collection failed: {error}")
            else:
                logger.info(f"[OK] {name} data collected ({len(items)} items)")
            all_opportunities.extend(items)
        except Exception as e:
            warnings.append(f"{name}: {e}")
            logger.error(f"[{name}] Unexpected error: {e}")

    logger.info(f"Total raw items: {len(all_opportunities)}")

    if not all_opportunities:
        logger.warning("No data collected from any source.")
        _send_report(store, entities, signals, breakout, [], [], warnings)
        return

    # 2. Entity Resolution
    logger.info("--- Phase 2: Entity Resolution ---")
    for opp in all_opportunities:
        entity = entities.find_or_create(
            opp.name, opp.url, opp.category, opp.description
        )
        if opp.url and not entity.url:
            entity.url = opp.url
        for tag in opp.tags:
            if tag not in entity.tags:
                entity.tags.append(tag)
        if opp.source not in entity.signal_sources:
            entity.signal_sources.append(opp.source)
        for sid in opp.source_ids:
            if sid not in entity.signal_sources:
                entity.signal_sources.append(sid)
    logger.info(f"[OK] Entities normalized ({len(entities.get_all())} entities)")

    # 3. Generate Signals
    logger.info("--- Phase 3: Signal Generation ---")
    _generate_signals(all_opportunities, entities, signals)
    logger.info(f"[OK] Signals generated ({len(signals.signals)} total)")

    # 4. Score
    logger.info("--- Phase 4: Scoring ---")
    macro_events = _extract_macro_events(all_opportunities)
    scorer = Scorer(entities, signals, macro_events, history=breakout.history)
    scored = scorer.score_all()
    logger.info(f"[OK] Opportunities scored ({len(scored)} entities)")

    # 5. History & Breakout
    logger.info("--- Phase 5: History & Breakout Detection ---")
    for s in scored:
        s.previous_score = 0
        entries = breakout.history.get(s.entity.id, {}).get("entries", [])
        if entries:
            s.previous_score = entries[-1].get("score", 0)
        s.score_change = s.score.total - s.previous_score

        breakout.update(
            s.entity.id,
            s.score.total,
            s.confidence,
            s.entity.signal_counts,
            s.entity.signal_sources,
        )
    breakouts_raw = breakout.detect_breakouts(BREAKOUT_THRESHOLD)
    logger.info(f"[OK] History updated, breakouts: {len(breakouts_raw)}")

    # Enrich breakout data with entity names
    breakouts = []
    for b in breakouts_raw:
        entity = entities.get(b["entity_id"])
        if entity:
            b["name"] = entity.name
            b["url"] = entity.url
            breakouts.append(b)

    # 6. Selection (section-based, max 30)
    logger.info("--- Phase 6: Selection ---")
    sections = build_sections(scored)
    logger.info(f"[OK] Sections built, total items: {total_count(sections)}")

    # 7. Watchlist
    watchlist_ids = breakout.get_watchlist_ids()
    watchlist = []
    for wid in watchlist_ids:
        entity = entities.get(wid)
        if entity:
            watchlist.append({
                "name": entity.name,
                "url": entity.url,
                "score": next((s.score.total for s in scored if s.entity.id == wid), 0),
                "first_seen": entity.first_seen,
            })

    # 8. Macro signals
    macro_signals = []
    for s in scored:
        if s.score.macro_adjustment != 0:
            for reason in s.reasons:
                if "Macro" in reason:
                    macro_signals.append(reason)
                    break
    macro_signals = list(dict.fromkeys(macro_signals))

    # 9. Save everything
    logger.info("--- Phase 7: Saving Data ---")
    entities.save()
    signals.save()
    signals.cleanup_old(days=90)
    breakout.save()
    _save_raw_data(scored)
    logger.info("[OK] Data saved")

    # 10. Send report
    _send_report(store, entities, signals, breakout, sections, breakouts, warnings, watchlist, macro_signals, scored)

    logger.info("=== Opportunity Scanner Complete ===")


def _generate_signals(opportunities, entities, signals):
    for opp in opportunities:
        entity = entities.find_similar(opp.name, opp.url)
        if not entity:
            entity = entities.find_or_create(opp.name, opp.url, opp.category, opp.description)

        categories = _detect_signal_categories(opp)
        for cat, desc in categories:
            signals.add_for_entity(entity.id, cat, opp.source, desc, 1, opp.url)

        _enrich_funding_metadata(opp, entity, signals)

        if opp.metrics.github_stars and opp.metrics.github_stars > 100:
            signals.add_for_entity(entity.id, "github", opp.source,
                                   f"GitHub stars: {opp.metrics.github_stars}", 1)
        if opp.metrics.hackernews_points and opp.metrics.hackernews_points > 100:
            signals.add_for_entity(entity.id, "community", opp.source,
                                   f"HN points: {opp.metrics.hackernews_points}", 1)
        if opp.metrics.producthunt_votes and opp.metrics.producthunt_votes > 50:
            signals.add_for_entity(entity.id, "community", opp.source,
                                   f"PH votes: {opp.metrics.producthunt_votes}", 1)
        if opp.metrics.news_mentions and opp.metrics.news_mentions > 0:
            signals.add_for_entity(entity.id, "news", opp.source,
                                   opp.description[:100], 1)


def _enrich_funding_metadata(opp, entity, signals):
    """Parse funding info from an opportunity and enrich the entity.

    Adds: startup_stage, funding_history, investors, accelerators,
    total_funding_m, plus funding_round / smart_money / accelerator signals.
    Never fabricates numbers — only records what text contains.
    """
    text = f"{opp.name} {opp.description}"
    parsed = parse_funding_event(text)
    accelerator = None
    if parsed:
        accelerator = parsed.get("accelerator")

    # YC / accelerator-tagged items count as accelerator-backed
    tags = [t.lower() for t in (opp.tags or [])]
    if opp.source == "ycombinator" or "yc" in tags:
        accelerator = "y combinator"

    if parsed and parsed.get("round") and parsed["round"] != UNKNOWN:
        round_stage = parsed["round"]
        stage_order = [UNKNOWN, "PRE_SEED", "SEED", "SERIES_A", "SERIES_B", "SERIES_C", "GROWTH", "PUBLIC"]
        if entity.startup_stage in stage_order and round_stage in stage_order:
            if stage_order.index(round_stage) > stage_order.index(entity.startup_stage):
                entity.startup_stage = round_stage

        amount = parsed.get("amount_m")
        investors = parsed.get("investors", [])
        round_entry = {
            "date": date.today().isoformat(),
            "round": round_stage,
            "amount_m": amount,
            "investors": investors,
        }
        if not _round_exists(entity.funding_history, round_entry):
            entity.funding_history.append(round_entry)

        signals.add_for_entity(
            entity.id, "funding_round", opp.source,
            f"Funding round: {STAGE_LABELS.get(round_stage, round_stage)}"
            + (f" {amount:.1f}M" if amount is not None else "")
            + (f" - {', '.join(investors[:3])}" if investors else ""),
            1, opp.url,
        )

        for inv in investors:
            if inv not in entity.investors:
                entity.investors.append(inv)
        if investors:
            signals.add_for_entity(
                entity.id, "smart_money", opp.source,
                f"Notable investors: {', '.join(investors[:4])}", 1, opp.url,
            )

    if accelerator:
        if accelerator not in entity.accelerators:
            entity.accelerators.append(accelerator)
        signals.add_for_entity(
            entity.id, "accelerator", opp.source,
            f"Accelerator: {accelerator}", 1, opp.url,
        )

    _recompute_funding_totals(entity)


def _round_exists(history: list[dict], candidate: dict) -> bool:
    for h in history:
        if (h.get("round") == candidate["round"]
                and h.get("amount_m") == candidate["amount_m"]
                and h.get("date") == candidate["date"]):
            return True
    return False


def _recompute_funding_totals(entity):
    amounts = [r.get("amount_m") for r in entity.funding_history if r.get("amount_m") is not None]
    if amounts:
        entity.total_funding_m = round(sum(amounts), 2)


def _detect_signal_categories(opp) -> list[tuple[str, str]]:
    text = (opp.name + " " + opp.description).lower()
    cat_lower = opp.category.lower()
    tags_lower = [t.lower() for t in opp.tags]
    results = []

    if any(w in text for w in ["raised", "funding", "seed round", "series a",
                                "series b", "series c", "investment", "investors"]):
        results.append(("funding", f"Funding signal: {opp.description[:80]}"))

    if any(w in text for w in ["hiring", "job opening", "looking for", "recruit",
                                "headcount", "team grow"]):
        results.append(("hiring", f"Hiring signal: {opp.description[:80]}"))

    if any(w in text for w in ["launch", "launched", "release", "released",
                                "announcing", "new product", "just shipped"]):
        results.append(("product_launch", f"Product event: {opp.description[:80]}"))

    if any(w in text for w in ["partner", "partnership", "collaboration",
                                "integrat", "alliance"]):
        results.append(("partnership", f"Partnership: {opp.description[:80]}"))

    if any(w in text for w in ["customer", "user growth", "traction", "milestone",
                                "arr", "mrr", "revenue"]):
        results.append(("customer", f"Customer signal: {opp.description[:80]}"))

    if "github" in tags_lower or "github" in cat_lower:
        results.append(("github", f"GitHub activity: {opp.description[:80]}"))

    if "producthunt" in tags_lower or "kickstarter" in tags_lower:
        results.append(("product_launch", f"Product launch: {opp.description[:80]}"))

    if "economy" in cat_lower or "macro" in tags_lower:
        results.append(("macro_event", f"Macro event: {opp.description[:80]}"))

    if "market" in cat_lower or "market_event" in cat_lower:
        results.append(("market_event", f"Market event: {opp.description[:80]}"))

    if any(w in text for w in ["acqui", "merger", "m&a", "buyout"]):
        results.append(("ma_signal", f"M&A signal: {opp.description[:80]}"))

    if any(w in cat_lower for w in ["funding", "ipo"]):
        results.append(("funding", f"Funding category: {opp.description[:80]}"))

    if not results:
        results.append(("news", opp.description[:100]))

    return results


def _extract_macro_events(opportunities) -> list[dict]:
    events = []
    for opp in opportunities:
        if opp.category == "Economy":
            desc = opp.description.lower()
            if "rate" in desc and "cut" in desc:
                events.append({"type": "rate_cut"})
            elif "rate" in desc and "hike" in desc:
                events.append({"type": "rate_hike"})
            if "cpi" in desc:
                events.append({"type": "cpi_low"})
            if "gdp" in desc and "growth" in desc:
                events.append({"type": "gdp_growth"})
    return events


def _send_report(store, entities, signals, breakout, sections, breakouts,
                 warnings, watchlist=None, macro_signals=None, scored=None):
    logger.info("--- Phase 8: Email Sending ---")
    scored = scored or []

    # Score trends (last up-to-5 history entries per shown entity)
    trends = {}
    for sec in sections:
        for s in sec["items"]:
            history_entries = breakout.history.get(s.entity.id, {}).get("entries", [])
            vals = [e.get("score", 0) for e in history_entries[-5:]]
            if vals:
                trends[s.entity.id] = vals

    html = render_email(
        sections=sections,
        breakouts=breakouts[:BREAKOUT_N],
        watchlist=(watchlist or [])[:5],
        warnings=warnings,
        macro_signals=macro_signals,
        trends=trends,
    )

    subject = build_subject(total_count(sections))
    send_email(html, subject)


def _save_raw_data(scored: list[ScoredEntity]):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    path = DATA_DIR / f"raw_{today}.json"
    data = []
    for s in scored:
        data.append({
            "entity": s.entity.to_dict(),
            "score": s.score.to_dict(),
            "confidence": s.confidence,
            "types": s.types,
            "reasons": s.reasons,
        })
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info(f"Raw data saved: {path}")


if __name__ == "__main__":
    main()
