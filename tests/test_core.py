from __future__ import annotations

import tempfile
import shutil
from datetime import datetime
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
    assert normalize_name("삼성전자 주식회사") == "삼성전자 주식회사"
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


def test_aggregator_domain_no_merge():
    """Distinct articles on the same portal domain must NOT collapse.

    Two different Google News items share news.google.com; merging by domain
    polluted one entity with unrelated signals (the 100-point 'Trump pushes
    Fed' false positive). Only exact-name and GitHub-repo matching may merge.
    """
    store, tmp = _make_store()
    try:
        em = EntityManager(store)
        e1 = em.find_or_create("OpenAI raises $1B",
                               "https://news.google.com/rss/articles/aaa", "Funding", "x")
        e2 = em.find_or_create("Samsung unveils chip",
                               "https://news.google.com/rss/articles/bbb", "Product", "y")
        assert len(em.get_all()) == 2, f"expected 2 entities, got {len(em.get_all())}"
        assert e1.id != e2.id
        assert em.find_similar("OpenAI raises $1B",
                               "https://techcrunch.com/2026/09/09/openai") is e1
        g1 = em.find_or_create("Repo Alpha", "https://github.com/acme/alpha",
                               "Open Source", "x")
        assert em.find_similar("Repo Beta", "https://github.com/acme/alpha") is g1
        g2 = em.find_or_create("Repo Gamma", "https://github.com/acme/gamma",
                               "Open Source", "y")
        assert g1.id != g2.id
        print("PASS: test_aggregator_domain_no_merge")
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
    html = render_email(sections, [], [], [],
                        source_status={"startups": {"status": "OK", "items": 3}},
                        report_links=[("임시 링크", "https://example.com")])
    assert "Palladium Daily Intelligence" in html
    assert "TestCo" in html
    assert "72" in html
    assert "스타트업" in html
    assert "주요 투자자 참여" in html
    assert "신규 이벤트" in html
    assert "최대 50개" in html
    assert "데이터 수집 상태" in html
    assert "임시 링크" in html
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
    assert total_count(sections) <= 50
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


# ---------------------------------------------------------------------------
# Korea: 한국 분류 / 원화 파싱 / 섹션 분리 / 최대 50개
# ---------------------------------------------------------------------------

def test_korean_entity_detection():
    from src.intelligence.classification import is_korean_entity
    assert is_korean_entity("삼성전자") is True
    assert is_korean_entity("카카오뱅크", url="https://www.kakaobank.com") is True
    assert is_korean_entity("Naver Labs", tags=["korea"]) is True
    assert is_korean_entity("Hyundai Motor") is True
    assert is_korean_entity("KOSPI", tags=[]) is True
    assert is_korean_entity("Acme Inc", url="https://acme.example") is False
    assert is_korean_entity("Apple", url="https://apple.com") is False
    assert is_korean_entity("SK Hynix") is True
    assert is_korean_entity("LG Electronics") is True
    assert is_korean_entity("Elon Musk's Boring Company") is False
    assert is_korean_entity("Big Energy Report") is False
    assert is_korean_entity("Body Shop") is False
    print("PASS: test_korean_entity_detection")


def test_full_korea_sections(test_kr="all"):
    from src.intelligence.selection import (
        build_sections, bucket_for, total_count,
        KOREA_STARTUP_BUCKET, KOREA_PUBLIC_BUCKET, KOREA_TECH_BUCKET,
    )
    kr_startup = mk_entity("kr1", "한빛 AI", "Funding", is_korean=True,
                           startup_stage="SERIES_A",
                           funding_history=[{"date": "2026-09-01", "round": "SERIES_A",
                                             "amount_m": 12000.0, "currency": "KRW",
                                             "investors": [], "status": "confirmed"}])
    kr_public = mk_entity("kr2", "한국전력", "Market Event", is_korean=True,
                          ticker="015760", entity_type="PUBLIC_COMPANY",
                          signal_counts={"market_event": 1})
    kr_tech = mk_entity("kr3", "국산 반도체 기술", "Technology", is_korean=True,
                        signal_counts={"github": 1})

    global_one = mk_entity("g1", "GlobalCo", "Startup", is_korean=False,
                           startup_stage="SEED")

    def b55():
        return ScoreBreakdown(funding=30, news=10, hiring=10, product=5)

    scored = [
        ScoredEntity(kr_startup, b55(), confidence=70, entity_type="STARTUP"),
        ScoredEntity(kr_public, b55(), confidence=70, entity_type="PUBLIC_COMPANY"),
        ScoredEntity(kr_tech, b55(), confidence=70, entity_type="OTHER"),
        ScoredEntity(global_one, b55(), confidence=70, entity_type="STARTUP"),
    ]
    assert bucket_for(scored[0]) == KOREA_STARTUP_BUCKET
    assert bucket_for(scored[1]) == KOREA_PUBLIC_BUCKET
    assert bucket_for(scored[2]) == KOREA_TECH_BUCKET

    sections = build_sections(scored)
    korea_items = [s.entity.name for sec in sections
                   if "한국" in sec["title"] for s in sec["items"]]
    global_items = [s.entity.name for sec in sections
                    if "한국" not in sec["title"] for s in sec["items"]]
    assert "한빛 AI" in korea_items
    assert "한국전력" in korea_items
    assert "국산 반도체 기술" in korea_items
    assert "GlobalCo" in global_items
    assert "한빛 AI" not in global_items
    assert total_count(sections) == 4
    print("PASS: test_korean_sections_separate")


def test_max_50_cap_no_padding():
    from src.intelligence.selection import build_sections, total_count
    items = []
    for i in range(50):
        en = mk_entity(f"m{i}", f"QualityCo{i}", "Startup", is_korean=(i % 2 == 0),
                       startup_stage="SEED")
        items.append(ScoredEntity(en, ScoreBreakdown(funding=40, news=10, hiring=5,
                                                     signal_diversity=4, cross_source=3),
                                  confidence=55))
    sections = build_sections(items)
    assert total_count(sections) <= 50, total_count(sections)

    # 낮은 점수(39)는 50개를 채우기 위해 포함하지 않는다.
    low = ScoredEntity(mk_entity("pad", "PadCo", "Startup"),
                       ScoreBreakdown(funding=7, news=2, product=30))
    sections2 = build_sections(items + [low])
    ids = [s.entity.id for sec in sections2 for s in sec["items"]]
    assert "pad" not in ids
    print("PASS: test_max_50_cap_no_padding")


def test_korean_funding_parse_and_krw():
    ev = parse_funding_event("한빛 AI, 시리즈 A 120억 원 투자 유치")
    assert ev is not None and ev["found"] is True
    assert ev["status"] == "confirmed"
    assert ev["round"] == "SERIES_A"
    assert ev["currency"] == "KRW"
    assert ev["amount_m"] == 12000.0

    ev2 = parse_funding_event("○○테크, 시드 5억 원 투자 유치")
    assert ev2["round"] == "SEED"

    ev3 = parse_funding_event("모기업, 1조 원 대규모 투자 유치")
    assert ev3["currency"] == "KRW"
    assert ev3["amount_m"] == 1_000_000.0

    assert "120억 원" == format_amount_kr(12000.0, "KRW")
    assert "5억 원" == format_amount_kr(500.0, "KRW")
    assert "1조 원" == format_amount_kr(1_000_000.0, "KRW")
    assert "500만 원" in format_amount_kr(5.0, "KRW")
    assert "5,000만 달러" == format_amount_kr(50.0, "USD")
    print("PASS: test_korean_funding_parse_and_krw")


def test_korean_amount_not_mistaken_for_usd():
    from src.intelligence.scoring import Scorer

    store, tmp = _make_store()
    try:
        em = EntityManager(store)
        sm = SignalManager(store)

        e = em.find_or_create("크레도스파트너스", "https://example.com", "Startup", "투자 회사")
        e.entity_type = "STARTUP"
        e.funding_history = [
            {"date": "2026-09-11", "round": "SERIES_A", "amount_m": 1500.0,
             "currency": "KRW", "investors": [], "status": "confirmed"},
        ]
        e.signal_sources = ["startuptoday"]
        sm.add_for_entity(e.id, "funding_round", "startuptoday", "투자 유치: 시리즈 A 15억 원", 1)

        e2 = em.find_or_create("대우산업", "https://example.com", "Startup", "기업")
        e2.entity_type = "STARTUP"
        e2.funding_history = [
            {"date": "2026-09-11", "round": "SERIES_A", "amount_m": 1_000_000.0,
             "currency": "KRW", "investors": [], "status": "confirmed"},
        ]
        e2.signal_sources = ["hankyung"]
        sm.add_for_entity(e2.id, "funding_round", "hankyung", "투자 유치: 시리즈 A 1조 원", 1)

        scorer = Scorer(em, sm)
        by_name = {s.entity.name: s for s in scorer.score_all()}
        kr_15ok = " ".join(format_reasons(by_name["크레도스파트너스"]))
        kr_1jo = " ".join(format_reasons(by_name["대우산업"]))

        assert "5억 달러 이상" not in kr_15ok
        assert "15억 달러" not in kr_15ok
        assert "투자 유치 신호" in kr_15ok
        assert "1조 원 이상" in kr_1jo
    finally:
        shutil.rmtree(tmp)
    print("PASS: test_korean_amount_not_mistaken_for_usd")


def test_record_round_stores_currency():
    from src.main import _record_round

    e = Entity("r1", "RoundCo", "https://round.co", "Startup", "x")
    _record_round(e, "SERIES_A", 12000.0, [], "confirmed", "KRW")
    assert e.funding_history[0]["currency"] == "KRW"
    _record_round(e, "SERIES_A", 20.0, [], "confirmed", "USD")
    assert e.funding_history[1]["currency"] == "USD"
    print("PASS: test_record_round_stores_currency")


def test_korean_withdrawal():
    ev = parse_funding_event("위즈봇, 시리즈 B 300억 원 투자 유치 철회")
    assert ev is not None
    assert ev["status"] == "withdrawn"
    print("PASS: test_korean_withdrawal")


# ---------------------------------------------------------------------------
# Palladium: Opportunity Type / Evidence Quality / Trajectory / Convergence
# ---------------------------------------------------------------------------

def test_palladium_opportunity_type():
    from src.analyzers.opptype import opportunity_type

    product = ScoredEntity(mk_entity("o1", "CoolApp", "Product", entity_type="PRODUCT"),
                           ScoreBreakdown(product=30, news=10, hiring=10))
    assert opportunity_type(product) == "BUILD"

    funded_product = ScoredEntity(
        mk_entity("o2", "CoolApp", "Product", entity_type="PRODUCT",
                  funding_history=[{"round": "SEED", "amount_m": 3.0, "status": "confirmed"}]),
        ScoreBreakdown(funding=40, product=10))
    assert opportunity_type(funded_product) == "INVEST"

    startup = ScoredEntity(mk_entity("o3", "StartupCo", "Startup", entity_type="STARTUP"),
                           ScoreBreakdown(funding=30, news=10, hiring=10))
    assert opportunity_type(startup) == "INVEST"

    acq = ScoredEntity(mk_entity("o4", "TargetCo", "M&A", entity_type="PRIVATE_COMPANY",
                                 event_types=["ACQUISITION"]),
                       ScoreBreakdown(news=30, funding=20))
    assert opportunity_type(acq) == "ACQUIRE"

    pub = ScoredEntity(mk_entity("o5", "PubCo", "Market Event", entity_type="PUBLIC_COMPANY",
                                 ticker="AAPL"),
                       ScoreBreakdown(news=40, funding=10))
    assert opportunity_type(pub) == "WATCH"

    low = ScoredEntity(mk_entity("o6", "LowCo", "Startup", entity_type="STARTUP"),
                       ScoreBreakdown(news=1))
    assert opportunity_type(low) == "IGNORE"
    print("PASS: test_palladium_opportunity_type")


def test_palladium_evidence_quality():
    from src.analyzers.evidence import evidence_quality

    official = mk_entity("q1", "국민은행", "Market Event",
                         entity_type="PUBLIC_COMPANY", domain="kb.co.kr",
                         signal_sources=["korea_news:google_news", "dart:fss"])
    assert evidence_quality(official) == "VERY_HIGH"

    mainstream = mk_entity("q2", "GlobalCo", "Startup", domain="x.example",
                           signal_sources=["techcrunch", "reuters"])
    assert evidence_quality(mainstream) == "HIGH"

    low = mk_entity("q3", "Shady", "Startup", domain="x.example",
                    signal_sources=["reddit"])
    assert evidence_quality(low) == "LOW"
    print("PASS: test_palladium_evidence_quality")


def test_palladium_trajectory_lifecycle():
    from src.analyzers.trajectory import trajectory, lifecycle

    rising = [{"date": "2026-09-08", "score": 40},
              {"date": "2026-09-09", "score": 52},
              {"date": "2026-09-10", "score": 66},
              {"date": "2026-09-11", "score": 85}]
    assert trajectory(rising) == "ACCELERATING"

    declining = [{"date": "2026-09-08", "score": 80},
                 {"date": "2026-09-09", "score": 70},
                 {"date": "2026-09-10", "score": 60},
                 {"date": "2026-09-11", "score": 52}]
    assert trajectory(declining) == "MOMENTUM_DECAY"
    assert trajectory([{"date": "2026-09-11", "score": 60}]) == "STABLE"

    def mk_scored(total, eid="lc1"):
        e = mk_entity(eid, "LifecycleCo", "Startup", entity_type="STARTUP")
        return ScoredEntity(e, ScoreBreakdown(funding=total, news=0))

    assert lifecycle(mk_scored(60), [{"date": "2026-09-09", "score": 52},
                                     {"date": "2026-09-10", "score": 55}]) == "WATCH"
    assert lifecycle(mk_scored(75), [{"date": "2026-09-09", "score": 70},
                                     {"date": "2026-09-10", "score": 72}]) == "BREAKOUT"
    assert lifecycle(mk_scored(85), [{"date": "2026-09-08", "score": 71},
                                     {"date": "2026-09-09", "score": 79},
                                     {"date": "2026-09-10", "score": 81}]) == "HIGH_PRIORITY"
    assert lifecycle(mk_scored(40), [{"date": "2026-09-10", "score": 55}]) == "DECAY"
    print("PASS: test_palladium_trajectory_lifecycle")


def test_palladium_convergence():
    from src.analyzers.convergence import convergence_categories

    e = mk_entity("c1", "GrowthCo", "Startup",
                  signal_counts={"funding": 2, "hiring": 1, "github": 3, "community": 1})
    cats = convergence_categories(e, e.signal_counts)
    assert "funding" in cats
    assert "hiring" in cats
    assert "github" in cats

    e2 = mk_entity("c2", "QuietCo", "Startup", signal_counts={"news": 1})
    assert convergence_categories(e2, e2.signal_counts) == []
    print("PASS: test_palladium_convergence")


def test_palladium_second_order():
    from src.analyzers.second_order import detect_second_order

    ai = ScoredEntity(mk_entity("s1", "AI 스타트업", "AI/ML",
                                entity_type="STARTUP", description="LLM 기반 AI 모델 서비스"),
                      ScoreBreakdown(funding=40, news=15, hiring=15, community=5))
    out = detect_second_order([ai], [])
    assert any(o["status"] == "Derived" for o in out)
    assert len(out) == 1

    macro = detect_second_order([], [{"type": "rate_cut", "broad": False}])
    assert any(o["status"] == "Macro" for o in macro)
    print("PASS: test_palladium_second_order")


def test_palladium_markdown_reports():
    from src.reports.markdown_report import render_markdown_reports
    from src.intelligence.selection import build_sections

    def b55():
        return ScoreBreakdown(funding=40, news=10, hiring=10, product=5)

    e1 = mk_entity("m1", "SeedKorea", "Startup", is_korean=True,
                   entity_type="STARTUP", startup_stage="SEED")
    e2 = mk_entity("m2", "GlobalStart", "Startup",
                   entity_type="STARTUP", startup_stage="SEED")
    items = [
        ScoredEntity(e1, b55(), confidence=70, entity_type="STARTUP"),
        ScoredEntity(e2, b55(), confidence=70, entity_type="STARTUP"),
    ]
    # Real GitHub-metric entity surfaced by the dedicated tech-trend rule. It
    # is passed via `scored` (not in sections) to prove the rule reads real
    # metrics independently of the quality-gated section buckets.
    ghi = mk_entity("m3", "OpenSourceTrend", "AI/ML", is_korean=False,
                    entity_type="OPEN_SOURCE_PROJECT",
                    signal_sources=["github_trending", "github:owner/repo"],
                    github_metrics={"stars": 45000, "stars_today": 3200,
                                    "forks": 1200, "language": "Python"})
    scored = items + [ScoredEntity(ghi, b55(), confidence=60,
                                   entity_type="OPEN_SOURCE_PROJECT")]
    sections = build_sections(items)
    files = render_markdown_reports(
        sections, scored, [], [], [], {"startups": {"status": "OK", "items": 5}},
        datetime(2026, 9, 11, 10, 10),
        "2026-09-10 10:10 ~ 2026-09-11 10:10 KST", [], [],
    )
    assert "daily-summary.md" in files
    assert "opportunities.md" in files
    assert "startup-radar.md" in files
    assert "korea-company.md" in files
    assert "market-anomaly.md" in files
    assert "deal-mna.md" in files
    assert "tech-trend.md" in files
    assert "product-opportunity.md" in files
    assert "dart-events.md" in files
    assert "company-growth.md" in files
    assert "second-order.md" in files
    assert "market-entry.md" in files
    assert "real-estate.md" in files
    assert "감지된 공개시장 이상 징후" in files["market-anomaly.md"]
    assert "# ⚡ Palladium Daily Summary" in files["daily-summary.md"]
    assert "SeedKorea" in files["korea-company.md"]
    assert "GlobalStart" in files["startup-radar.md"]
    assert "OpenSourceTrend" in files["tech-trend.md"]
    assert "3,200" in files["tech-trend.md"]
    assert "45,000" in files["tech-trend.md"]
    print("PASS: test_palladium_markdown_reports")


def test_market_entry_brand_extraction():
    from src.collectors.market_entry import extract_global_brand

    assert extract_global_brand("ChatGPT, 한국 시장 본격 진출") == "ChatGPT"
    assert extract_global_brand("Perplexity, 국내 출시 임박") == "Perplexity"
    assert extract_global_brand("OpenAI, 한국에 사무소 설립") == "OpenAI"
    # Korean-only transcription (no usable Latin token) → None, never guessed.
    assert extract_global_brand("챗GPT 한국 출시 예정") is None
    assert extract_global_brand("AI 반도체 한국 시장 확대") is None
    # Media/broadcast codes and English fillers are never brands.
    assert extract_global_brand("YTN 뉴스, KBS 보도") is None
    assert extract_global_brand("The Korea Times 영어 기사") is None
    print("PASS: test_market_entry_brand_extraction")


def test_market_entry_report_rule():
    from src.reports.markdown_report import render_markdown_reports

    def b55():
        return ScoreBreakdown(funding=40, news=10, hiring=10, product=5)

    # Non-Korean global product with Korean-media coverage → candidate even at
    # low score (below the section gate).
    nk = mk_entity("me1", "Perplexity", "AI/ML", is_korean=False,
                   entity_type="PRODUCT",
                   signal_sources=["korea_news:market_entry"])
    # Korean subject with the same coverage → must NOT be a market-entry target.
    kr = mk_entity("me2", "네이버", "Product", is_korean=True, entity_type="PRODUCT",
                   signal_sources=["korea_news"])
    items = [
        ScoredEntity(nk, ScoreBreakdown(news=2), confidence=40),
        ScoredEntity(kr, b55(), confidence=70),
    ]
    files = render_markdown_reports([], items, [], [], [], {},
                                    datetime(2026, 9, 11, 10, 10),
                                    "2026-09-10 10:10 ~ 2026-09-11 10:10 KST", [], [])
    assert "Perplexity" in files["market-entry.md"]
    assert "네이버" not in files["market-entry.md"]
    print("PASS: test_market_entry_report_rule")


def test_tech_trend_no_fabrication():
    from src.reports.markdown_report import render_markdown_reports

    def b55():
        return ScoreBreakdown(funding=40, news=10, hiring=10, product=5)

    # Real-looking metrics but NO technology-collector signal this cycle →
    # must NOT surface (unverified numbers are never presented).
    ghost = mk_entity("tt1", "GhostMetrics", "AI/ML",
                      entity_type="OPEN_SOURCE_PROJECT",
                      signal_sources=["official"],
                      github_metrics={"stars": 99999, "stars_today": 5000,
                                      "forks": 99, "language": "Rust"})
    # Collector signal present but no real metrics → not listed.
    nom = mk_entity("tt2", "NoMetrics", "AI/ML",
                    entity_type="OPEN_SOURCE_PROJECT",
                    signal_sources=["github_trending"],
                    github_metrics=None)
    items = [ScoredEntity(ghost, b55()), ScoredEntity(nom, b55())]
    files = render_markdown_reports(
        [], items, [], [], [], {}, datetime(2026, 9, 11, 10, 10),
        "2026-09-10 10:10 ~ 2026-09-11 10:10 KST", [], [],
    )
    assert "GhostMetrics" not in files["tech-trend.md"]
    assert "NoMetrics" not in files["tech-trend.md"]
    assert "기술 트렌드 신호가 없습니다" in files["tech-trend.md"]
    print("PASS: test_tech_trend_no_fabrication")


def test_real_estate_parse_and_format():
    from src.collectors.real_estate import format_amount_manwon, _parse_trades

    xml = """<?xml version="1.0" encoding="UTF-8"?>
<response>
  <body>
    <items>
      <item>
        <거래금액>215,000</거래금액>
        <건축년도>2010</건축년도>
        <년>2026</년>
        <법정동>반포동</법정동>
        <아파트>래미안퍼스티지</아파트>
        <월>8</월>
        <일>15</일>
        <전용면적>84.9900</전용면적>
        <층>7</층>
      </item>
      <item>
        <거래금액>1,500</거래금액>
        <년>2026</년>
        <월>8</월>
        <일>2</일>
        <전용면적>59.9400</전용면적>
        <층>3</층>
      </item>
      <item>
        <거래금액></거래금액>
        <년>2026</년>
        <월>8</월>
        <일>1</일>
      </item>
    </items>
  </body>
</response>"""
    trades = _parse_trades(xml)
    assert len(trades) == 2
    t = trades[0]
    assert t["apt"] == "래미안퍼스티지"
    assert t["amount_manwon"] == 215000
    assert t["deal_date"] == "2026-08-15"
    assert t["area"] == 84.99
    assert t["floor"] == 7
    assert t["build_year"] == 2010
    assert format_amount_manwon(215000) == "21억5,000만 원"
    assert format_amount_manwon(10000) == "1억 원"
    assert format_amount_manwon(1500) == "1,500만 원"
    print("PASS: test_real_estate_parse_and_format")


def test_real_estate_report_rule():
    from src.reports.markdown_report import render_markdown_reports
    from src import timeutil

    re_dict = {
        "region": "강남구",
        "trades": [
            {"apt": "래미안퍼스티지", "area": 84.99, "floor": 7,
             "build_year": 2010, "amount_manwon": 215000,
             "deal_date": "2026-08-15"},
            {"apt": "반포자이", "amount_manwon": 120000,
             "deal_date": "2026-08-10"},
        ],
    }
    today = timeutil.date_kst()
    listed = mk_entity("re1", "래미안퍼스티지 (강남구)", "Real Estate",
                       is_korean=True, real_estate=re_dict, last_seen=today,
                       signal_sources=["real_estate"])
    stale = mk_entity("re2", "구라미 (강남구)", "Real Estate", is_korean=True,
                      real_estate=re_dict, last_seen="2026-08-01",
                      signal_sources=["real_estate"])
    items = [
        ScoredEntity(listed, ScoreBreakdown(news=2), confidence=40),
        ScoredEntity(stale, ScoreBreakdown(news=2), confidence=40),
    ]
    files = render_markdown_reports(
        [], items, [], [], [], {}, datetime(2026, 9, 11, 10, 10),
        "2026-09-10 10:10 ~ 2026-09-11 10:10 KST", [], [],
    )
    md = files["real-estate.md"]
    assert "래미안퍼스티지" in md and "구라미" not in md
    assert "21억5,000만 원" in md
    assert "## 강남구" in md

    # No real_estate rows at all → explicit empty-state.
    empty = render_markdown_reports(
        [], [], [], [], [], {}, datetime(2026, 9, 11, 10, 10),
        "2026-09-10 10:10 ~ 2026-09-11 10:10 KST", [], [],
    )
    assert "감지된 실거래 기록이 없습니다" in empty["real-estate.md"]

    # API key missing → SKIPPED note about the key.
    skipped = render_markdown_reports(
        [], [], [], [], [], {"real_estate": {"status": "SKIPPED", "items": 0}},
        datetime(2026, 9, 11, 10, 10),
        "2026-09-10 10:10 ~ 2026-09-11 10:10 KST", [], [],
    )
    assert "REAL_ESTATE_API_KEY" in skipped["real-estate.md"]
    print("PASS: test_real_estate_report_rule")


def test_monthly_archive_pack_and_ordering():
    import zipfile
    from src.monthly import archive_month, pack_month

    base = Path(tempfile.mkdtemp())
    data_dir = base / "data"
    reports_dir = base / "reports"
    archive_dir = base / "archives"
    data_dir.mkdir()
    reports_dir.mkdir()
    try:
        (reports_dir / "2026-08").mkdir(parents=True)
        (reports_dir / "2026-08" / "daily-summary.md").write_text("# t", encoding="utf-8")
        (data_dir / "raw_2026-08-31.json").write_text("{}", encoding="utf-8")
        (data_dir / "entities.json").write_text("{}", encoding="utf-8")

        zip_path = pack_month("2026-08", data_dir, reports_dir, archive_dir)
        with zipfile.ZipFile(zip_path) as z:
            names = z.namelist()
        assert any(n == "reports/2026-08/daily-summary.md" for n in names)
        assert any(n == "data/raw_2026-08-31.json" for n in names)
        assert any(n == "state/entities.json" for n in names)
        assert "metadata/archive.json" in names

        # publish=False → packed but NOT verified, nothing deleted.
        res1 = archive_month("2026-08", publish=False, delete=True,
                             data_dir=data_dir, reports_dir=reports_dir,
                             archive_dir=archive_dir)
        assert res1["verified"] is False
        assert res1["deleted"] == 0
        assert (reports_dir / "2026-08" / "daily-summary.md").exists()

        # publisher raises → upload unverified → nothing deleted.
        def boom(month, asset):
            raise RuntimeError("upload failed")

        res2 = archive_month("2026-08", publish=True, delete=True,
                             publisher=boom, data_dir=data_dir,
                             reports_dir=reports_dir, archive_dir=archive_dir)
        assert res2["verified"] is False
        assert res2["deleted"] == 0

        # publisher returns URL → verified → deletion proceeds.
        def ok(month, asset):
            return f"https://example.com/releases/tag/{month}"

        res3 = archive_month("2026-08", publish=True, delete=True, publisher=ok,
                             data_dir=data_dir, reports_dir=reports_dir,
                             archive_dir=archive_dir)
        assert res3["verified"] is True
        assert res3["deleted"] >= 2
        assert not (reports_dir / "2026-08").exists()
        assert not list(data_dir.glob("raw_2026-08*.json"))

        # No data at all → skip gracefully, nothing deleted.
        empty_base = Path(tempfile.mkdtemp())
        res4 = archive_month("2026-01", data_dir=empty_base / "data",
                             reports_dir=empty_base / "reports",
                             archive_dir=archive_dir)
        assert res4["archive"] is None
        assert res4["verified"] is False
    finally:
        for p in (base, empty_base) if "empty_base" in dir() else (base,):
            if p is not None and p.exists():
                shutil.rmtree(p)
    print("PASS: test_monthly_archive_pack_and_ordering")


def test_previous_month_kst():
    from datetime import datetime
    from src.monthly import previous_month_kst
    assert previous_month_kst(datetime(2026, 1, 5)) == "2025-12"
    assert previous_month_kst(datetime(2026, 9, 1)) == "2026-08"


if __name__ == "__main__":
    test_normalize_name()
    test_extract_domain()
    test_entity_manager()
    test_aggregator_domain_no_merge()
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
    test_korean_entity_detection()
    test_full_korea_sections()
    test_max_50_cap_no_padding()
    test_korean_funding_parse_and_krw()
    test_korean_amount_not_mistaken_for_usd()
    test_record_round_stores_currency()
    test_korean_withdrawal()
    test_palladium_opportunity_type()
    test_palladium_evidence_quality()
    test_palladium_trajectory_lifecycle()
    test_palladium_convergence()
    test_palladium_second_order()
    test_palladium_markdown_reports()
    test_tech_trend_no_fabrication()
    test_market_entry_brand_extraction()
    test_market_entry_report_rule()
    test_real_estate_parse_and_format()
    test_real_estate_report_rule()
    test_monthly_archive_pack_and_ordering()
    test_previous_month_kst()
    print("\nAll tests passed!")