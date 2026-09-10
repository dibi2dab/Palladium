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

    html = render_email([scored], [], [], [])
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


if __name__ == "__main__":
    test_normalize_name()
    test_extract_domain()
    test_entity_manager()
    test_signal_manager()
    test_scorer()
    test_breakout_detector()
    test_email_rendering()
    test_formatter()
    print("\nAll tests passed!")
