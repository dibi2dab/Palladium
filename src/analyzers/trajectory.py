"""Trajectory & Lifecycle — long-run score behavior over history entries.

Derived purely from the BreakoutDetector history (scores on days we ran).
Entries look like: {"date": "...", "score": N, ...}.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from src.palladium_config import trajectory_rules, score_bands

if TYPE_CHECKING:
    from src.intelligence.scoring import ScoredEntity

# Trajectory
ACCELERATING = "ACCELERATING"
GROWING = "GROWING"
STABLE = "STABLE"
MOMENTUM_DECAY = "MOMENTUM_DECAY"

TRAJ_LABELS = {
    ACCELERATING: "가속 상승",
    GROWING: "상승",
    STABLE: "안정",
    MOMENTUM_DECAY: "모멘텀 약화",
}

# Lifecycle
EMERGING = "EMERGING"
BREAKOUT = "BREAKOUT"
HIGH_PRIORITY = "HIGH_PRIORITY"
WATCH = "WATCH"
DECAY = "DECAY"

LIFECYCLE_LABELS = {
    EMERGING: "급부상",
    BREAKOUT: "돌파",
    HIGH_PRIORITY: "최우선 유지",
    WATCH: "관찰",
    DECAY: "하강",
}


def _scores(entries: list[dict] | None) -> list[int]:
    if not entries:
        return []
    return [int(e.get("score", 0) or 0) for e in entries if isinstance(e, dict)]


def trajectory(entries: list[dict] | None) -> str:
    rules = trajectory_rules()
    window = rules.get("window", 5)
    accel_delta = rules.get("accel_delta", 10)
    decay_delta = rules.get("decay_delta", -10)

    scores = _scores(entries)[-window:]
    if len(scores) < rules.get("min_entries", 3):
        return STABLE  # not enough data to call a direction

    deltas = [scores[i + 1] - scores[i] for i in range(len(scores) - 1)]
    total = sum(deltas)
    if total >= accel_delta and deltas[-1] >= deltas[0]:
        return ACCELERATING
    if total <= decay_delta:
        return MOMENTUM_DECAY
    if total > 0:
        return GROWING
    return STABLE


def lifecycle(scored: ScoredEntity, entries: list[dict] | None) -> str:
    bands = score_bands()
    prior = _scores(entries)
    prev_score = prior[-1] if prior else 0
    total = scored.score.total
    priority = bands.get("priority", 80)
    emerging = bands.get("emerging", 70)
    watch = bands.get("watch", 50)

    if total < watch:
        return DECAY if prev_score >= watch else WATCH
    if total >= priority and len(prior) >= 3:
        return HIGH_PRIORITY
    if total >= emerging:
        if prev_score >= emerging:
            return BREAKOUT
        return EMERGING
    return WATCH


def traj_label(code: str) -> str:
    return TRAJ_LABELS.get(code, STABLE)


def lifecycle_label(code: str) -> str:
    return LIFECYCLE_LABELS.get(code, WATCH)