from __future__ import annotations

import tempfile
import shutil
from pathlib import Path

from src.models import Opportunity, Metrics, ScoreBreakdown, Analysis
from src.processing.normalizer import normalize_opportunity, extract_domain, normalize_url
from src.processing.deduplicator import deduplicate
from src.processing.filter import filter_candidates
from src.ai.analyzer import AIAnalyzer
from src.history.tracker import HistoryTracker
from src.report.email_template import render_email


def test_normalize_opportunity():
    opp = Opportunity(
        name="  Test Repo  ",
        url="https://github.com/test/repo",
        description="A test project",
        category="AI/ML",
        source="github_trending",
    )
    result = normalize_opportunity(opp)
    assert result.name == "Test Repo"
    assert result.category == "AI/ML"
    print("PASS: test_normalize_opportunity")


def test_extract_domain():
    assert extract_domain("https://github.com/test/repo") == "github.com"
    assert extract_domain("https://www.example.com") == "example.com"
    print("PASS: test_extract_domain")


def test_deduplicate():
    opp1 = Opportunity(
        name="Test",
        url="https://github.com/test/repo",
        description="Test project",
        category="AI/ML",
        source="github_trending",
        source_ids=["github:test/repo"],
    )
    opp2 = Opportunity(
        name="Test2",
        url="https://news.ycombinator.com/item?id=123",
        description="HN post about test",
        category="AI/ML",
        source="hackernews",
        source_ids=["github:test/repo"],
    )
    unique = deduplicate([opp1, opp2])
    assert len(unique) == 1
    assert len(unique[0].source_ids) >= 1
    print("PASS: test_deduplicate")


def test_filter():
    good = Opportunity(
        name="Good Project",
        url="https://github.com/good/project",
        description="A high quality project with real value",
        category="AI/ML",
        source="github_trending",
    )
    spam = Opportunity(
        name="spam",
        url="https://spam.com",
        description="earn money fast click here",
        category="Other",
        source="spam",
    )
    filtered = filter_candidates([good, spam])
    assert len(filtered) == 1
    assert filtered[0].name == "Good Project"
    print("PASS: test_filter")


def test_ai_analyzer_defaults():
    opp = Opportunity(
        name="Test",
        url="https://github.com/test/repo",
        description="Test project",
        category="AI/ML",
        source="github_trending",
    )
    analyzer = AIAnalyzer()
    result = analyzer.analyze_batch([opp])
    assert len(result) == 1
    assert result[0].types == ["WATCH"]
    print("PASS: test_ai_analyzer_defaults")


def test_history_tracker():
    tmp = Path(tempfile.mkdtemp())
    try:
        tracker = HistoryTracker(data_dir=tmp)
        opp = Opportunity(
            name="Test",
            url="https://github.com/test/repo",
            description="Test",
            category="AI/ML",
            source="github_trending",
            metrics=Metrics(github_stars=1000),
        )
        opp.total_score = 75
        opp.types = ["WATCH"]
        tracker.record_opportunity(opp)
        tracker.save()

        tracker2 = HistoryTracker(data_dir=tmp)
        assert len(tracker2.opportunities) == 1
        assert tracker2.opportunities[opp.id]["latest_score"] == 75
        print("PASS: test_history_tracker")
    finally:
        shutil.rmtree(tmp)


def test_email_template():
    opp = Opportunity(
        name="Test Project",
        url="https://github.com/test/project",
        description="A great project for testing",
        category="AI/ML",
        source="github_trending",
        metrics=Metrics(github_stars=5000),
    )
    opp.total_score = 85
    opp.types = ["BUILD"]
    opp.confidence = "High"
    opp.analysis = Analysis(
        reasoning="Strong growth potential",
        facts=["5000 stars"],
        inferences=["Growing fast"],
    )
    html = render_email([opp], [], [])
    assert "OPPORTUNITY SCANNER" in html
    assert "Test Project" in html
    assert "85" in html
    assert "BUILD" in html
    print("PASS: test_email_template")


if __name__ == "__main__":
    test_normalize_opportunity()
    test_extract_domain()
    test_deduplicate()
    test_filter()
    test_ai_analyzer_defaults()
    test_history_tracker()
    test_email_template()
    print("\nAll tests passed!")
