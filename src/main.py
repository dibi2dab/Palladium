from __future__ import annotations

import json
import logging
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("palladium")

from src.config import (
    DATA_DIR, REPORTS_DIR, AI_ENABLED, TOP_N, BREAKOUT_N, BREAKOUT_THRESHOLD,
    MAX_CANDIDATES_FOR_AI, REPO_URL, REPO_BRANCH,
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
from src.collectors.korea import KoreaNewsCollector, DartCollector
from src.intelligence.entities import EntityManager
from src.intelligence.signals import SignalManager
from src.intelligence.scoring import Scorer, ScoredEntity
from src.intelligence.breakout import BreakoutDetector
from src.intelligence.selection import build_sections, total_count
from src.intelligence.funding import (
    UNKNOWN, parse_funding_event, format_amount_kr, STAGE_LABELS_KO,
)
from src.intelligence import classification
from src.analyzers import second_order as second_order_mod
from src.report.email_template import render_email
from src.report.email_sender import send_email, build_subject
from src.reports.markdown_report import render_markdown_reports, report_links
from src import timeutil


COLLECTOR_MAP = {
    "startups": StartupCollector,
    "funding": FundingCollector,
    "markets": MarketCollector,
    "economy": EconomyCollector,
    "products": ProductCollector,
    "technology": TechnologyCollector,
    "news": NewsCollector,
    "reddit": RedditCollector,
    "korea_news": KoreaNewsCollector,
    "dart": DartCollector,
}


def main():
    logger.info("=== Palladium Starting ===")
    warnings: list[str] = []

    store = JsonStore()
    entities = EntityManager(store)
    signals = SignalManager(store)
    breakout = BreakoutDetector(store)

    meta = store.load_meta()
    prev_collected_at = meta.get("last_collected_at", "")
    generated_at = timeutil.now_kst()

    # 1. Collect
    logger.info("--- Phase 1: Data Collection ---")
    all_opportunities = []
    source_status: dict[str, dict] = {}
    for name, cls in COLLECTOR_MAP.items():
        try:
            collector = cls()
            items, error = collector.safe_collect()
            if error:
                warnings.append(f"{name}: {error}")
                logger.warning(f"[{name}] Collection failed: {error}")
                source_status[name] = {"status": "FAILED", "items": 0}
            else:
                logger.info(f"[OK] {name} data collected ({len(items)} items)")
                if name == "dart" and not items:
                    source_status[name] = {"status": "SKIPPED", "items": 0}
                else:
                    source_status[name] = {"status": "OK", "items": len(items)}
            all_opportunities.extend(items)
        except Exception as e:
            warnings.append(f"{name}: {e}")
            logger.error(f"[{name}] Unexpected error: {e}")
            source_status[name] = {"status": "FAILED", "items": 0}

    logger.info(f"Total raw items: {len(all_opportunities)}")

    if not all_opportunities:
        logger.warning("No data collected from any source.")
        _send_report(store, entities, signals, breakout, [], [], warnings)
        return

    # 2. Entity Resolution
    logger.info("--- Phase 2: Entity Resolution ---")
    for opp in all_opportunities:
        entity = _resolve_entity(entities, opp)
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

    # 6. Selection (section-based, max 50; global + separate Korea sections)
    logger.info("--- Phase 6: Selection ---")
    sections = build_sections(scored)
    logger.info(f"[OK] Sections built, total items: {total_count(sections)}")
    logger.info(f"[OK] Sections: " + ", ".join(
        f"{s['title']}={len(s['items'])}" for s in sections))

    # Second-order (derived) opportunities — rule-based chains.
    second_order = second_order_mod.detect_second_order(scored, macro_events)
    logger.info(f"[OK] Second-order chains: {len(second_order)}")

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
    store.save_meta({"last_collected_at": generated_at.isoformat()})
    logger.info("[OK] Data saved")

    # 10. Send report
    window = _collection_window(prev_collected_at, generated_at)
    _send_report(store, entities, signals, breakout, sections, breakouts, warnings,
                 watchlist, macro_signals, scored,
                 generated_at=generated_at, collection_window=window,
                 source_status=source_status, second_order=second_order,
                 macro_events=macro_events)

    logger.info("=== Palladium Complete ===")


def _resolve_entity(entities, opp):
    ent = entities.find_similar(opp.name, opp.url)
    if ent:
        return ent
    return entities.find_or_create(opp.name, opp.url, opp.category, opp.description)


def _generate_signals(opportunities, entities, signals):
    for opp in opportunities:
        entity = _resolve_entity(entities, opp)

        if not entity.is_korean and classification.is_korean_entity(
            opp.name, opp.url, opp.tags, opp.category,
        ):
            entity.is_korean = True
            if "korea" not in entity.tags:
                entity.tags.append("korea")

        parsed = parse_funding_event(opp.name, opp.description or "")
        events = classification.classify_events(
            opp.name, opp.description or "", opp.category, opp.tags, parsed,
        )
        entities_type = classification.classify_entity_type(
            opp.name, opp.url, opp.category, opp.tags, opp.source,
            description=opp.description,
        )
        if entities_type != classification.OTHER and entity.entity_type == classification.OTHER:
            entity.entity_type = entities_type
        if not entity.parent_company:
            entity.parent_company = classification.extract_parent_company(opp.name)

        for etype in events:
            entity.add_event(etype, opp.description, opp.url)

        _handle_funding(opp, entity, parsed, signals)

        tags = [t.lower() for t in (opp.tags or [])]
        if opp.source == "ycombinator" or "yc" in tags or "accelerator" in tags:
            _record_accelerator(entity, "y combinator", opp.source, opp.url, signals)

        categories = _detect_signal_categories(opp, parsed, events)
        for cat, desc, key in categories:
            desc = (desc or opp.description[:100]).strip()
            signals.add_or_merge(entity.id, cat, opp.source, desc, 1, opp.url, key)

        if opp.metrics.github_stars and opp.metrics.github_stars > 100:
            signals.add_or_merge(entity.id, "github", opp.source,
                                 f"GitHub 스타 {opp.metrics.github_stars}", 1,
                                 opp.url, "github-stars")
        if opp.metrics.hackernews_points and opp.metrics.hackernews_points > 100:
            signals.add_or_merge(entity.id, "community", opp.source,
                                 f"Hacker News 점수 {opp.metrics.hackernews_points}", 1,
                                 opp.url, f"hn:{opp.metrics.hackernews_points}")
        if opp.metrics.producthunt_votes and opp.metrics.producthunt_votes > 50:
            signals.add_or_merge(entity.id, "community", opp.source,
                                 f"Product Hunt 추천 {opp.metrics.producthunt_votes}", 1,
                                 opp.url, f"ph:{opp.metrics.producthunt_votes}")
        if opp.metrics.news_mentions and opp.metrics.news_mentions > 0:
            signals.add_for_entity(entity.id, "news", opp.source,
                                   opp.description[:100], 1, opp.url)


def _handle_funding(opp, entity, parsed, signals):
    """Record funding events without fabricating data.

    - withdrawn: negative signal only (funding_withdrawn)
    - planned:   amount/round noted as planned, NO positive signal
    - confirmed: positive funding_round signal + round history

    Cross-source confirmation is handled by add_or_merge using the SAME
    dedupe key for the same round (TechCrunch + Reuters + blog = 1 signal
    with strength 3, not 3 separate boosts).
    """
    if not parsed or not parsed.get("found"):
        return
    status = parsed.get("status", "confirmed")
    round_stage = parsed.get("round") or UNKNOWN
    amount = parsed.get("amount_m")
    investors = parsed.get("investors", [])
    accelerator = parsed.get("accelerator")

    _set_funding_status(entity, status)

    if status == "withdrawn":
        signals.add_or_merge(entity.id, "funding_withdrawn", opp.source,
                             f"투자 유치 무산/철회: {opp.name}", 1, opp.url,
                             f"withdrawn:{round_stage}")
        return

    currency = parsed.get("currency")

    if status == "planned":
        _record_round(entity, round_stage, amount, investors, "planned", currency)
        logger.debug(f"Planned funding for {opp.name}")
        return

    _record_round(entity, round_stage, amount, investors, "confirmed", currency)

    if round_stage != UNKNOWN:
        stage_order = [UNKNOWN, "PRE_SEED", "SEED", "SERIES_A", "SERIES_B",
                       "SERIES_C", "GROWTH", "PUBLIC"]
        if entity.startup_stage in stage_order and round_stage in stage_order:
            if stage_order.index(round_stage) > stage_order.index(entity.startup_stage):
                entity.startup_stage = round_stage
        signals.add_or_merge(
            entity.id, "funding_round", opp.source,
            f"투자 유치: {STAGE_LABELS_KO.get(round_stage, round_stage)}"
            + (f" {format_amount_kr(amount, parsed.get('currency', 'USD'))}"
               if amount is not None else ""),
            1, opp.url, f"round:{round_stage}",
        )

    for inv in investors:
        if inv not in entity.investors:
            entity.investors.append(inv)
        signals.add_or_merge(entity.id, "smart_money", opp.source,
                             f"주요 투자자: {inv}", 1, opp.url,
                             f"inv:{inv}")

    if accelerator:
        _record_accelerator(entity, accelerator, opp.source, opp.url, signals)

    _recompute_funding_totals(entity)


def _set_funding_status(entity, status):
    # worst-known status wins: withdrawn > planned > confirmed
    priority = {"": 0, "confirmed": 1, "planned": 2, "withdrawn": 3}
    if priority.get(status, 0) > priority.get(entity.funding_status, 0):
        entity.funding_status = status


def _record_round(entity, round_stage, amount, investors, status, currency=None):
    entry = {
        "date": date.today().isoformat(),
        "round": round_stage,
        "amount_m": amount,
        "investors": investors,
        "status": status,
    }
    if currency:
        entry["currency"] = currency
    if not _round_exists(entity.funding_history, entry):
        entity.funding_history.append(entry)


def _round_exists(history: list[dict], candidate: dict) -> bool:
    for h in history:
        if (h.get("round") == candidate["round"]
                and h.get("amount_m") == candidate["amount_m"]
                and h.get("date") == candidate["date"]):
            return True
    return False


def _record_accelerator(entity, accelerator, source, url, signals):
    if accelerator not in entity.accelerators:
        entity.accelerators.append(accelerator)
    signals.add_or_merge(entity.id, "accelerator", source,
                         f"액셀러레이터: {accelerator}", 1, url,
                         f"accel:{accelerator}")


def _recompute_funding_totals(entity):
    amounts = [r.get("amount_m") for r in entity.funding_history
               if r.get("amount_m") is not None
               and r.get("status", "confirmed") == "confirmed"
               and r.get("currency", "USD") != "KRW"]
    if amounts:
        entity.total_funding_m = round(sum(amounts), 2)


def _detect_signal_categories(opp, parsed, events) -> list[tuple[str, str, str | None]]:
    """Map classified event types to signal categories (dedupe-aware)."""
    results: list[tuple[str, str, str | None]] = []

    for etype in events:
        etext = (opp.name + " " + opp.description).strip()
        if etype == classification.FUNDING:
            # confirmed rounds are handled once by _handle_funding; planned
            # and withdrawn rounds are intentionally NOT positive signals.
            continue
        elif etype == classification.MARKET_EVENT:
            results.append(("market_event", f"시장 이벤트: {etext[:80]}", "market"))
        elif etype == classification.ACQUISITION:
            results.append(("ma_signal", f"인수합병: {etext[:80]}", "ma"))
        elif etype == classification.PRODUCT_LAUNCH:
            results.append(("product_launch", f"제품 출시: {etext[:80]}", "product"))
        elif etype == classification.PARTNERSHIP:
            results.append(("partnership", f"파트너십: {etext[:80]}", "partner"))
        elif etype == classification.HIRING:
            results.append(("hiring", f"채용: {etext[:80]}", "hiring"))
        elif etype == classification.COMMUNITY_GROWTH:
            results.append(("community", f"커뮤니티 성장: {etext[:80]}", "community"))
        elif etype == classification.EARNINGS:
            results.append(("news", f"실적: {etext[:80]}", None))
        elif etype == classification.CONTRACT:
            results.append(("customer", f"대형 계약: {etext[:80]}", "contract"))

    seen: set[str] = set()
    deduped = []
    for cat, desc, key in results:
        if ("funding" in cat.upper() or key) and key in seen:
            continue
        if key:
            seen.add(key)
        deduped.append((cat, desc, key))

    if opp.category.lower() == "economy" or "macro" in [t.lower() for t in opp.tags]:
        deduped.append(("macro_event", f"거시경제: {opp.description[:80]}", "macro"))

    if not deduped:
        deduped.append(("news", opp.description[:100], None))
    return deduped


def _extract_macro_events(opportunities) -> list[dict]:
    events = []
    seen: set[str] = set()
    for opp in opportunities:
        if not opp.category or opp.category.lower() != "economy":
            continue
        desc = opp.description.lower()
        macro_type = None
        broad = False
        if "rate" in desc and "cut" in desc:
            macro_type = "rate_cut"
        elif "rate" in desc and "hike" in desc:
            macro_type = "rate_hike"
        if "cpi" in desc:
            macro_type = "cpi_high" if ("up" in desc or "high" in desc
                                        or "rise" in desc or "surge" in desc) else "cpi_low"
        if "gdp" in desc:
            if "grow" in desc:
                macro_type, broad = "gdp_growth", True
            elif "contract" in desc or "decline" in desc or "fall" in desc:
                macro_type, broad = "gdp_decline", True
        if "employment" in desc or "unemployment" in desc or "jobs" in desc:
            if "strong" in desc or "fall" in desc or "low" in desc:
                macro_type, broad = "employment_strong", True
            elif "weak" in desc or "rise" in desc:
                macro_type, broad = "employment_weak", True
        if "oil" in desc and "price" in desc:
            macro_type = "oil_price_up" if ("up" in desc or "rise" in desc
                                            or "high" in desc or "surge" in desc) else "oil_price_down"
        if macro_type and macro_type not in seen:
            seen.add(macro_type)
            events.append({"type": macro_type, "broad": broad})
    return events


def _send_report(store, entities, signals, breakout, sections, breakouts,
                 warnings, watchlist=None, macro_signals=None, scored=None,
                 generated_at=None, collection_window="",
                 source_status=None, second_order=None, macro_events=None):
    logger.info("--- Phase 8: Markdown Reports & Email Sending ---")
    scored = scored or []
    generated_at = generated_at or timeutil.now_kst()
    source_status = source_status or {}
    second_order = second_order or []

    # Score trends (last up-to-5 history entries per shown entity)
    trends = {}
    for sec in sections:
        for s in sec["items"]:
            history_entries = breakout.history.get(s.entity.id, {}).get("entries", [])
            vals = [e.get("score", 0) for e in history_entries[-5:]]
            if vals:
                trends[s.entity.id] = vals

    # Markdown reports (reports/<date>/*.md).
    md_files = render_markdown_reports(
        sections=sections,
        scored=scored,
        macro_events=macro_events or [],
        macro_signals=macro_signals or [],
        breakouts=breakouts or [],
        source_status=source_status,
        generated_at=generated_at,
        collection_window=collection_window,
        second_order=second_order,
        watchlist=watchlist or [],
    )
    _save_markdown_reports(md_files, generated_at)

    date_iso = generated_at.strftime("%Y-%m-%d")
    all_links = report_links(date_iso, REPO_URL, REPO_BRANCH)
    report_link_list: list[tuple[str, str]] = []
    for name, url in all_links.items():
        if name in md_files:
            label = name.replace("-", " ").replace(".md", "")
            report_link_list.append((label, url))

    html = render_email(
        sections=sections,
        breakouts=breakouts[:BREAKOUT_N],
        watchlist=(watchlist or [])[:5],
        warnings=warnings,
        macro_signals=macro_signals,
        trends=trends,
        generated_at=timeutil.korean_datetime_str(generated_at),
        collection_window=collection_window,
        source_status=source_status,
        report_links=report_link_list,
    )

    subject = build_subject(total_count(sections))
    send_email(html, subject)


def _save_markdown_reports(md_files: dict[str, str], generated_at):
    date_iso = generated_at.strftime("%Y-%m-%d")
    out_dir = REPORTS_DIR / date_iso
    out_dir.mkdir(parents=True, exist_ok=True)
    # Remove stale domain files: a domain with no items today must not keep
    # yesterday's content on disk.
    for old in out_dir.glob("*.md"):
        if old.name != "README.md" and old.name not in md_files:
            old.unlink()
    for name, content in md_files.items():
        path = out_dir / name
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info(f"Markdown report saved: {path}")
    # GitHub Actions commit step watches this file so reports are stored.
    marker = out_dir / "README.md"
    if not marker.exists():
        marker.write_text(
            f"# Palladium Daily Intelligence — {date_iso}\n\n"
            "자동 생성된 Markdown 일일 보고서입니다. (규칙 기반, AI 없음)\n",
            encoding="utf-8",
        )


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
            "news_importance": s.news_importance,
            "entity_type": s.entity_type,
            "event_types": s.event_types,
            "judgement": s.judgement,
            "reasons": s.reasons,
            "conf_evidence": s.conf_evidence,
            "opportunity_type": s.opportunity_type,
            "evidence_quality": s.evidence_quality,
            "trajectory": s.trajectory,
            "lifecycle": s.lifecycle,
            "convergence": s.convergence,
        })
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info(f"Raw data saved: {path}")


def _collection_window(prev_iso: str, generated_at) -> str:
    """'2026-09-10 10:10 ~ 2026-09-11 10:10 KST' — never exposes UTC."""
    try:
        start = datetime.fromisoformat(prev_iso) if prev_iso else None
    except ValueError:
        start = None
    if start is None:
        start = (generated_at - timedelta(days=1))
    return (f"{timeutil.kst_compact(start)} ~ "
            f"{timeutil.kst_compact(generated_at)} KST")


if __name__ == "__main__":
    main()
