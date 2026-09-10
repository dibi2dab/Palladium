from __future__ import annotations

import tempfile
import shutil
from pathlib import Path

from src.intelligence.entities import EntityManager, Entity, compute_entity_id, normalize_name, extract_domain
from src.intelligence.signals import SignalManager, Signal
from src.intelligence.scoring import Scorer, ScoreBreakdown
from src.intelligence.breakout import BreakoutDetector
from src.storage.json_store import JsonStore
from src.report.email_template import render_email
from src.report.formatter import format_reasons, format_score_change


def _make_store():
    tmp = Path(tempfile.mkdtemp())
    return JsonStore(data_dir=tmp), tmp


def test_normalize_name():
    assert normalize_name("  Hello World  ") == "hello world"
    assert normalize_name("OpenAI") == "openai"
    assert normalize_name("Test@#$ Corp") == "test corp"
    print("PASS: test_normalize_name")


def test_extract_domain():
    assert extract_domain("https://github.com/test/repo") == "github.com"
    assert extract_domain("https://www.example.com/path") == "example.com"
    assert extract_domain("") == ""
    print("PASS: test_extract_domain")


def test_entity_manager():
    store, tmp = _make_store()
    try:
        em = EntityManager(store)
        e1 = em.find_or_create("TestCo", "https://testco.com", "SaaS", "A test company")
        e2 = em.find_or_create("TestCo", "https://testco.com")
        assert e1.id == e2.id
        assert e1.name == "TestCo"
        assert len(em.get_all()) == 1
        em.save()
        em2 = EntityManager(store)
        assert len(em2.get_all()) == 1
        print("PASS: test_entity_manager")
    finally:
        shutil.rmtree(tmp)


def test_signal_manager():
    store, tmp = _make_store()
    try:
        sm = SignalManager(store)
        signal = sm.add_for_entity("ent1", "funding", "techcrunch", "Raised $5M")
        assert signal.entity_id == "ent1"
        assert signal.category == "funding"
        recent = sm.get_recent_signals("ent1")
        assert len(recent) == 1
        counts = sm.count_by_category("ent1")
        assert counts["funding"] == 1
        sm.save()
        print("PASS: test_signal_manager")
    finally:
        shutil.rmtree(tmp)


def test_scorer():
    store, tmp = _make_store()
    try:
        em = EntityManager(store)
        sm = SignalManager(store)

        e = em.find_or_create("HotStartup", "https://hotstartup.com", "AI/ML", "AI company")
        sm.add_for_entity(e.id, "funding", "techcrunch", "Raised $10M")
        sm.add_for_entity(e.id, "hiring", "wellfound", "Hiring 20 engineers")
        sm.add_for_entity(e.id, "product_launch", "producthunt", "New product launch")
        sm.add_for_entity(e.id, "community", "reddit", "Community growing")
        sm.add_for_entity(e.id, "news", "techcrunch", "Featured in article")
        e.signal_sources = ["techcrunch", "wellfound", "producthunt", "reddit"]

        scorer = Scorer(em, sm)
        scored = scorer.score_all()
        assert len(scored) == 1
        s = scored[0]
        assert s.score.total > 0
        assert s.confidence > 0
        assert len(s.types) > 0
        assert len(s.reasons) > 0
        print("PASS: test_scorer (score=" + str(s.score.total) + ", conf=" + str(s.confidence) + ")")
    finally:
        shutil.rmtree(tmp)


def test_breakout_detector():
    store, tmp = _make_store()
    try:
        bd = BreakoutDetector(store)
        # Simulate historical entry with a past date
        bd.history["ent1"] = {
            "entries": [{"date": "2026-01-01", "score": 50, "confidence": 60,
                         "signal_counts": {"funding": 1}, "sources": ["tc"]}],
            "first_seen": "2026-01-01",
        }
        bd.update("ent1", 80, 75, {"funding": 1, "hiring": 1}, ["tc", "wf"])
        breakouts = bd.detect_breakouts(threshold=20.0)
        assert len(breakouts) == 1
        assert breakouts[0]["prev_score"] == 50
        assert breakouts[0]["curr_score"] == 80
        bd.save()
        print("PASS: test_breakout_detector")
    finally:
        shutil.rmtree(tmp)


def test_email_rendering():
    from src.intelligence.entities import Entity
    from src.intelligence.scoring import ScoredEntity

    e = Entity("test123", "TestCo", "https://testco.com", "AI/ML", "A test company")
    s = ScoreBreakdown(funding=12, hiring=8, product=5, community=6, news=3, github=5,
                       partnership=0, customer=3, signal_diversity=8, cross_source=7,
                       macro_adjustment=0)
    scored = ScoredEntity(entity=e, score=s, confidence=72, types=["INVEST", "BUILD"],
                         reasons=["Funding signal (+12)", "Hiring activity (+8)"])

    sections = [{"title": "STARTUP & VENTURE", "items": [scored], "icon": "venture", "kind": "venture"}]
    html = render_email(sections, [], [], [])
    assert "OPPORTUNITY SCANNER" in html
    assert "TestCo" in html
    assert "72" in html
    assert "INVEST" in html
    assert "Funding signal" in html
    print("PASS: test_email_rendering")


def test_formatter():
    from src.intelligence.entities import Entity
    from src.intelligence.scoring import ScoredEntity

    e = Entity("test", "Co", "", "Cat", "")
    s = ScoreBreakdown(funding=10, hiring=5)
    scored = ScoredEntity(entity=e, score=s, confidence=50, types=["WATCH"],
                         reasons=["Funding signal (+10)"])
    reasons = format_reasons(scored)
    assert len(reasons) > 0
    assert "Funding" in reasons[0]

    change = format_score_change(60, 80)
    assert "60" in change and "80" in change and "+20" in change
    print("PASS: test_formatter")


def test_funding_analysis():
    from src.intelligence.funding import (
        parse_funding_event, parse_amount, detect_round, stage_advanced, format_amount,
    )

    ev = parse_funding_event("Acme Corp raises $3.5M Seed round led by Sequoia Capital")
    assert ev is not None
    assert ev["round"] == "SEED"
    assert ev["amount_m"] == 3.5
    assert "sequoia" in ev["investors"]

    ev2 = parse_funding_event("Acme Corp raises $18M Series A with a16z")
    assert ev2["round"] == "SERIES_A"
    assert "a16z" in ev2["investors"]

    assert parse_amount("$2M") == 2.0
    assert parse_amount("$1.5B") == 1500.0
    assert detect_round("Series B funding")[0] == "SERIES_B"
    assert stage_advanced(["SEED", "SERIES_A", "SERIES_B"]) is True
    assert stage_advanced(["SERIES_A"]) is False
    assert format_amount(3.0) == "$3M"
    assert format_amount(1200) == "$1.2B"
    print("PASS: test_funding_analysis")


def test_selection_buckets():
    from src.intelligence.entities import Entity
    from src.intelligence.scoring import ScoredEntity, ScoreBreakdown
    from src.intelligence.selection import build_sections, bucket_for

    mk = lambda eid, name, cat, tags=(), stage="UNKNOWN", ticker=None: Entity(
        eid, name, "https://x.example", cat, "desc"
    )
    e1 = mk("s1", "SeedCo", "Startup")
    e1.startup_stage = "SEED"
    e1.tags = ["startup"]
    e1.funding_history = [{"date": "2026-09-01", "round": "SEED", "amount_m": 3.0, "investors": []}]

    e2 = mk("t1", "Apple Watch", "Product")
    e2.tags = ["product"]
    e2.signal_counts = {"product_launch": 1}

    e3 = mk("p1", "ACME Corp", "Market Event")
    e3.ticker = "ACME"

    e4 = mk("m1", "MergerCo", "M&A")
    e4.signal_counts = {"ma_signal": 1}

    ee = Entity("e1a", "EarthCo", "https://earth.example", "Economy", "x")

    assert bucket_for(ScoredEntity(e1, ScoreBreakdown(funding=10))) == "startup"
    assert bucket_for(ScoredEntity(e3, ScoreBreakdown(news=3))) == "public"
    assert bucket_for(ScoredEntity(e4, ScoreBreakdown(news=3))) == "ma"
    assert bucket_for(ScoredEntity(ee, ScoreBreakdown(news=2))) == "macro"

    s1 = ScoredEntity(e1, ScoreBreakdown(funding=10), confidence=70, types=["VC_BACKED"])
    s2 = ScoredEntity(e2, ScoreBreakdown(product=5), confidence=60, types=["WATCH"])
    s3 = ScoredEntity(e3, ScoreBreakdown(news=3), confidence=50, types=["PUBLIC_MARKET"])
    s4 = ScoredEntity(e4, ScoreBreakdown(news=2), confidence=40, types=["M&A_TARGET"])

    # Extra startup entities so the section budget exceeds TOP_N
    extra_funds = []
    for i in range(6):
        en = Entity(f"sx{i}", f"Startup{i}", f"https://s{i}.example", "Startup", "d")
        en.startup_stage = "SEED"
        en.tags = ["startup"]
        extra_funds.append(ScoredEntity(en, ScoreBreakdown(funding=8), confidence=50, types=["EARLY_STAGE"]))

    sections = build_sections([s1, s2, s3, s4] + extra_funds)
    titles = [sc["title"] for sc in sections]
    assert any("STARTUP" in t for t in titles)
    assert any("PUBLIC" in t for t in titles)
    assert any("M&A" in t for t in titles)
    ids = [s.entity.id for sec in sections for s in sec["items"]]
    assert len(ids) == len(set(ids)), "duplicate entities in report"
    print("PASS: test_selection_buckets")


def test_funding_intelligence_score():
    from src.intelligence.entities import Entity
    from src.intelligence.scoring import Scorer, ScoreBreakdown
    from src.intelligence.signals import SignalManager

    store, tmp = _make_store()
    try:
        em = EntityManager(store)
        sm = SignalManager(store)
        e = em.find_or_create("VCBackedCo", "https://vcbacked.co", "Startup", "AI company")
        e.startup_stage = "SERIES_A"
        e.investors = ["sequoia capital"]
        e.accelerators = ["y combinator"]
        e.funding_history = [
            {"date": "2026-01-01", "round": "SEED", "amount_m": 1.0, "investors": []},
            {"date": "2026-09-01", "round": "SERIES_A", "amount_m": 20.0, "investors": ["sequoia"]},
        ]
        e.total_funding_m = 21.0
        e.signal_sources = ["techcrunch", "yc", "hn"]

        scorer = Scorer(em, sm)
        scored = scorer.score_all()
        s = scored[0]
        assert s.score.funding >= 7
        assert s.score.smart_money >= 5
        assert s.score.accelerator >= 6
        assert "VC_BACKED" in s.types or "EARLY_STAGE" in s.types or "GROWTH" in s.types
        print("PASS: test_funding_intelligence_score (total=" + str(s.score.total) + ")")
    finally:
        shutil.rmtree(tmp)


def test_big_tech_product_penalty():
    from src.intelligence.entities import Entity
    from src.intelligence.scoring import ScoreBreakdown
    from src.intelligence.signals import SignalManager

    store, tmp = _make_store()
    try:
        em = EntityManager(store)
        sm = SignalManager(store)
        e = em.find_or_create("Apple Watch Ultra", "https://apple.com", "Product", "New device")
        sm.add_for_entity(e.id, "product_launch", "news", "Apple launches new watch", 1)
        scorer = Scorer(em, sm)
        scored = scorer.score_all()
        assert scored[0].score.product <= 3
        print("PASS: test_big_tech_product_penalty")
    finally:
        shutil.rmtree(tmp)


if __name__ == "__main__":
    test_normalize_name()
    test_extract_domain()
    test_entity_manager()
    test_signal_manager()
    test_scorer()
    test_breakout_detector()
    test_email_rendering()
    test_formatter()
    test_funding_analysis()
    test_selection_buckets()
    test_funding_intelligence_score()
    test_big_tech_product_penalty()
    print("\nAll tests passed!")
