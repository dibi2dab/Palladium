from __future__ import annotations

import tempfile
import shutil
from pathlib import Path

from src.intelligence.entities import EntityManager, Entity, compute_entity_id, normalize_name, extract_domain
from src.intelligence.signals import SignalManager, Signal
from src.intelligence.scoring import Scorer, ScoreBreakdown, ScoredEntity
from src.intelligence.breakout import BreakoutDetector
from src.storage.json_store import JsonStore
from src.report.email_template import render_email
from src.report.formatter import format_reasons, format_score_change
from src.intelligence import classification
from src.intelligence.funding import (
    parse_funding_event, parse_amount, detect_round, stage_advanced,
    format_amount, format_amount_kr,
)


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
        assert s.entity_type
        assert len(s.reasons) > 0
        print("PASS: test_scorer (score=" + str(s.score.total) + ", conf=" + str(s.confidence) + ")")
    finally:
        shutil.rmtree(tmp)


def test_breakout_detector():
    store, tmp = _make_store()
    try:
        bd = BreakoutDetector(store)
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
    e = Entity("test123", "TestCo", "https://testco.com", "AI/ML", "A test company")
    s = ScoreBreakdown(funding=12, hiring=8, product=5, community=6, news=3, github=5,
                       partnership=0, customer=3, signal_diversity=8, cross_source=7,
                       macro_adjustment=0)
    scored = ScoredEntity(entity=e, score=s, confidence=72,
                          entity_type="STARTUP", event_types=["FUNDING", "PRODUCT_LAUNCH"],
                          judgement="ATTENTION",
                          reasons=["주요 투자자 참여 (Sequoia)", "성장 신호 4종"])

    sections = [{"title": "🚀 스타트업 & 벤처", "items": [scored], "icon": "venture", "kind": "venture"}]
    html = render_email(sections, [], [], [])
    assert "기회 스캐너" in html
    assert "TestCo" in html
    assert "72" in html
    assert "스타트업" in html
    assert "주요 투자자 참여" in html
    print("PASS: test_email_rendering")


def test_formatter():
    e = Entity("test", "Co", "", "Cat", "")
    s = ScoreBreakdown(funding=10, hiring=5)
    scored = ScoredEntity(entity=e, score=s, confidence=50,
                          entity_type="STARTUP", event_types=["FUNDING"],
                          reasons=["주요 투자자 참여 (Sequoia)"])
    reasons = format_reasons(scored)
    assert len(reasons) > 0
    assert "투자" in reasons[0]

    change = format_score_change(60, 80)
    assert "60" in change and "80" in change and "+20" in change
    print("PASS: test_formatter")


def test_funding_analysis():
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
    # Amounts in the final email text are Korean.
    assert "5,000만 달러" in format_amount_kr(50.0)
    assert "15억 달러" in format_amount_kr(1500.0)
    print("PASS: test_funding_analysis")


def mk_entity(eid, name, cat, **kw):
    e = Entity(eid, name, "https://x.example", cat, "desc")
    for k, v in kw.items():
        setattr(e, k, v)
    return e


def test_selection_buckets():
    from src.intelligence.selection import build_sections, bucket_for, total_count

    e1 = mk_entity("s1", "SeedCo", "Startup", startup_stage="SEED",
                   funding_history=[{"date": "2026-09-01", "round": "SEED",
                                     "amount_m": 3.0, "investors": []}])
    e2 = mk_entity("t1", "Apple Watch", "Product", signal_counts={"product_launch": 1})
    e3 = mk_entity("p1", "ACME Corp", "Market Event", ticker="ACME", entity_type="PUBLIC_COMPANY")
    e4 = mk_entity("m1", "MergerCo", "M&A", signal_counts={"ma_signal": 1})
    ee = Entity("e1a", "EarthCo", "https://earth.example", "Economy", "x")

    assert bucket_for(ScoredEntity(e1, ScoreBreakdown(funding=10))) == "startup"
    assert bucket_for(ScoredEntity(e2, ScoreBreakdown(product=5))) == "product"
    assert bucket_for(ScoredEntity(e3, ScoreBreakdown(news=3))) == "public"
    assert bucket_for(ScoredEntity(e4, ScoreBreakdown(news=3))) == "ma"
    assert bucket_for(ScoredEntity(ee, ScoreBreakdown(news=2))) == "macro"

    def b55(**kw):
        total = kw.get("funding", 0) + kw.get("smart_money", 0) + kw.get("hiring", 0) \
            + kw.get("product", 0) + kw.get("news", 0) + kw.get("community", 0) \
            + kw.get("signal_diversity", 0) + kw.get("cross_source", 0)
        return ScoreBreakdown(**kw) if total >= 50 else ScoreBreakdown(
            funding=30, news=10, hiring=10, product=5, **{k: v for k, v in kw.items()}
        )

    s1 = ScoredEntity(e1, b55(), confidence=70, entity_type="STARTUP", event_types=["FUNDING"])
    s2 = ScoredEntity(e2, b55(), confidence=60, entity_type="PRODUCT", event_types=["PRODUCT_LAUNCH"])
    s3 = ScoredEntity(e3, b55(), confidence=50, entity_type="PUBLIC_COMPANY", event_types=["MARKET_EVENT"])
    s4 = ScoredEntity(e4, b55(), confidence=40, entity_type="PRIVATE_COMPANY", event_types=["ACQUISITION"])

    extra_funds = []
    for i in range(6):
        en = mk_entity(f"sx{i}", f"Startup{i}", "Startup", startup_stage="SEED")
        extra_funds.append(ScoredEntity(en, ScoreBreakdown(funding=40, news=8, hiring=5,
                                                           signal_diversity=4, cross_source=3),
                                        confidence=50))

    sections = build_sections([s1, s2, s3, s4] + extra_funds)
    titles = " ".join(sc["title"] for sc in sections)
    assert "스타트업" in titles, titles
    assert "공개시장" in titles, titles
    assert "M&A" in titles, titles
    assert "제품" in titles, titles
    ids = [s.entity.id for sec in sections for s in sec["items"]]
    assert len(ids) == len(set(ids)), "duplicate entities in report"
    assert total_count(sections) <= 30
    print("PASS: test_selection_buckets")


def test_funding_intelligence_score():
    store, tmp = _make_store()
    try:
        em = EntityManager(store)
        sm = SignalManager(store)
        e = em.find_or_create("VCBackedCo", "https://vcbacked.co", "Startup", "AI company")
        e.entity_type = "STARTUP"
        e.event_types.append("FUNDING")
        e.startup_stage = "SERIES_A"
        e.investors = ["sequoia capital"]
        e.accelerators = ["y combinator"]
        e.funding_history = [
            {"date": "2026-01-01", "round": "SEED", "amount_m": 1.0, "investors": [], "status": "confirmed"},
            {"date": "2026-09-01", "round": "SERIES_A", "amount_m": 20.0, "investors": ["sequoia"], "status": "confirmed"},
        ]
        e.total_funding_m = 21.0
        e.signal_sources = ["techcrunch", "yc", "hn"]

        scorer = Scorer(em, sm)
        scored = scorer.score_all()
        s = scored[0]
        assert s.score.funding >= 7
        assert s.score.smart_money >= 5
        assert s.score.accelerator >= 6
        assert s.entity_type == "STARTUP"
        assert "FUNDING" in s.event_types
        print("PASS: test_funding_intelligence_score (total=" + str(s.score.total) + ")")
    finally:
        shutil.rmtree(tmp)


def test_big_tech_product_penalty():
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


# ---------------------------------------------------------------------------
# Test 1–10: opportunity-quality requirements
# ---------------------------------------------------------------------------

def test_1_50m_seed_is_funding_event():
    """$50M Seed round -> FUNDING event + SEED stage, confirmed."""
    ev = parse_funding_event("Acme AI raises $50M Seed round")
    assert ev is not None
    assert ev["found"] is True
    assert ev["status"] == "confirmed"
    assert ev["round"] == "SEED"
    assert ev["amount_m"] == 50.0

    events = classification.classify_events("Acme AI raises $50M Seed round", "",
                                            "Funding", [], ev)
    assert classification.FUNDING in events
    entity_type = classification.classify_entity_type(
        "Acme AI", "", "Funding", [], description="raises $50M Seed round")
    assert entity_type == classification.STARTUP
    print("PASS: test_1_50m_seed_is_funding_event")


def test_2_scrubbed_round_is_non_positive():
    """A scrubbed/cancelled round must NOT produce a positive funding signal."""
    ev = parse_funding_event("Coreweave scrubbed a $500M funding round")
    assert ev is not None
    assert ev["status"] == "withdrawn"

    store, tmp = _make_store()
    try:
        em = EntityManager(store)
        sm = SignalManager(store)
        e = em.find_or_create("Coreweave", "https://coreweave.example", "Startup", "x")
        sm.add_or_merge(e.id, "funding_withdrawn", "reuters",
                        "Coreweave scrubbed a $500M funding round",
                        dedupe_key="withdrawn:UNKNOWN")
        sm.add_or_merge(e.id, "news", "reuters", "Coreweave cancels funding attempt")
        scorer = Scorer(em, sm)
        s = scorer.score_all()[0]
        assert s.score.funding == 0, f"funding score must be 0, got {s.score.funding}"
        assert e.funding_status in ("", "withdrawn")

        # Scenario 2: company had earlier confirmed rounds AND a positive
        # funding_round signal today, but the LATEST event is a withdrawal.
        e2 = em.find_or_create("ScrubbedCo", "https://scrubbed.example", "Startup", "x")
        e2.funding_status = "withdrawn"
        e2.funding_history = [
            {"date": "2026-08-01", "round": "SERIES_A", "amount_m": 30.0,
             "investors": [], "status": "confirmed"},
        ]
        sm.add_or_merge(e2.id, "funding_round", "techcrunch", "투자 유치: 시리즈 A",
                        dedupe_key="round:SERIES_A")
        s2 = Scorer(em, sm).score_all()
        s2 = next(x for x in s2 if x.entity.id == e2.id)
        assert s2.score.funding == 0, f"withdrawn status must zero funding, got {s2.score.funding}"
        print("PASS: test_2_scrubbed_round_is_non_positive")
    finally:
        shutil.rmtree(tmp)


def test_3_apple_unveils_is_product_with_parent():
    """'Apple unveils iPhone Duo' -> PRODUCT entity + parent_company=Apple."""
    title = "Apple unveils iPhone Duo"
    name = classification.extract_entity_name(title)
    parent = classification.extract_parent_company(title)
    assert name.lower().startswith("iphone"), name
    assert parent == "Apple", parent

    events = classification.classify_events(title, "", "Product", [])
    assert classification.PRODUCT_LAUNCH in events
    entity_type = classification.classify_entity_type(name, "", "Product", [])
    assert entity_type == classification.PRODUCT
    print("PASS: test_3_apple_unveils_is_product_with_parent")


def test_4_shopify_acquires_no_funding():
    """Acquisition headlines must not be misread as funding events."""
    title = "Shopify acquires Return Rabbit"
    ev = parse_funding_event(title, "Shopify acquires Return Rabbit to expand")
    assert ev is None, "an acquisition is not a funding event"

    events = classification.classify_events(title, "Shopify acquires Return Rabbit", "M&A", [])
    assert classification.ACQUISITION in events
    assert classification.FUNDING not in events
    print("PASS: test_4_shopify_acquires_no_funding")


def test_5_treasury_is_market_event():
    """Treasury/yield/bond commentary -> MARKET_EVENT, never a funding event."""
    title = "US 30-Year Treasury ETF yields rise further"
    body = "Bond market selloff pushes Treasury yields higher"
    ev = parse_funding_event(title, body)
    assert ev is None, "treasury news must not parse as funding"

    events = classification.classify_events(title, body, "Market Event", [])
    assert classification.MARKET_EVENT in events
    entity_type = classification.classify_entity_type(title, "", "Market Event", [])
    assert entity_type == classification.OTHER
    print("PASS: test_5_treasury_is_market_event")


def test_6_cross_source_merges():
    """Same round reported by 2 outlets = 1 signal, not 2 boosts."""
    store, tmp = _make_store()
    try:
        sm = SignalManager(store)
        s1 = sm.add_or_merge("e1", "funding_round", "techcrunch",
                             "투자 유치: 시리즈 A", 1, "https://tc", "round:SERIES_A")
        s2 = sm.add_or_merge("e1", "funding_round", "reuters",
                             "투자 유치: 시리즈 A", 1, "https://re", "round:SERIES_A")
        assert s1 is s2, "merged signals should return the same object"
        assert s2.strength == 2
        source_counts = sm.source_count_by_category("e1")
        assert source_counts["funding_round"] == 2, source_counts
        print("PASS: test_6_cross_source_merges")
    finally:
        shutil.rmtree(tmp)


def test_7_low_score_not_selected():
    """Score below 50 (e.g. 39) must never appear, even to pad TOP."""
    from src.intelligence.selection import build_sections, total_count

    low = ScoredEntity(mk_entity("low", "LowCo", "Startup"),
                       ScoreBreakdown(funding=7, news=2, product=30))  # total 39
    high = ScoredEntity(mk_entity("hi", "HighCo", "Startup"),
                        ScoreBreakdown(funding=40, news=10, hiring=10,
                                       signal_diversity=8, cross_source=7,
                                       product=10))  # total 85
    sections = build_sections([low, high])
    ids = [s.entity.id for sec in sections for s in sec["items"]]
    assert "low" not in ids, "39점 이하는 포함되면 안 됨"
    assert "hi" in ids
    assert total_count(sections) == 1
    print("PASS: test_7_low_score_not_selected")


def test_8_funding_plus_news_diversity():
    """Funding + News = 2 distinct signal kinds (score contribution capped)."""
    store, tmp = _make_store()
    try:
        em = EntityManager(store)
        sm = SignalManager(store)
        e = em.find_or_create("TwoSignalCo", "https://two.example", "Startup", "x")
        sm.add_or_merge(e.id, "funding_round", "techcrunch", "투자 유치: 시드",
                        dedupe_key="round:SEED")
        sm.add_or_merge(e.id, "news", "techcrunch", "보도 1건")
        scorer = Scorer(em, sm)
        s = scorer.score_all()[0]
        assert s.score.signal_diversity == 6, f"2종 → 6점, got {s.score.signal_diversity}"
        assert any("2종" in r for r in s.reasons), s.reasons
        print("PASS: test_8_funding_plus_news_diversity")
    finally:
        shutil.rmtree(tmp)


def test_9_irrelevant_macro_penalty_zero():
    """A macro headwind must not penalize an unrelated industry (0 effect)."""
    store, tmp = _make_store()
    try:
        em = EntityManager(store)
        sm = SignalManager(store)
        e = em.find_or_create("GenericTeaCo", "https://tea.example", "Food", "Tea maker")
        sm.add_for_entity(e.id, "news", "reuters", "Tea company news")
        scorer = Scorer(em, sm, macro_events=[{"type": "rate_hike"}])
        s = scorer.score_all()[0]
        assert s.score.macro_adjustment == 0, s.score.macro_adjustment

        fin = em.find_or_create("RocketBank", "https://bank.example", "Fintech", "Consumer banking")
        sm.add_for_entity(fin.id, "news", "reuters", "Bank news")
        scorer2 = Scorer(em, sm, macro_events=[{"type": "rate_hike"}])
        s2 = next(x for x in scorer2.score_all() if x.entity.id == fin.id)
        assert s2.score.macro_adjustment < 0, s2.score.macro_adjustment
        print("PASS: test_9_irrelevant_macro_penalty_zero")
    finally:
        shutil.rmtree(tmp)


def test_10_no_search_data_no_fabrication():
    """No search/interest data -> no fabricated search reasons or scores."""
    store, tmp = _make_store()
    try:
        em = EntityManager(store)
        sm = SignalManager(store)
        e = em.find_or_create("QuietCo", "https://quiet.example", "Startup", "x")
        e.search_interest = None
        e.news_momentum = None
        e.community_momentum = None
        e.hiring_growth = None
        scorer = Scorer(em, sm)
        s = scorer.score_all()[0]
        assert s.score.total == 0
        assert s.judgement == "EXCLUDED"
        assert not any("검색" in r or "search" in r.lower() for r in s.reasons)
        from src.intelligence.selection import build_sections
        assert build_sections([s])[0]["items"] == []
        print("PASS: test_10_no_search_data_no_fabrication")
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
    test_1_50m_seed_is_funding_event()
    test_2_scrubbed_round_is_non_positive()
    test_3_apple_unveils_is_product_with_parent()
    test_4_shopify_acquires_no_funding()
    test_5_treasury_is_market_event()
    test_6_cross_source_merges()
    test_7_low_score_not_selected()
    test_8_funding_plus_news_diversity()
    test_9_irrelevant_macro_penalty_zero()
    test_10_no_search_data_no_fabrication()
    print("\nAll tests passed!")