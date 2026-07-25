"""Tests for the rework brain — the free-tier auto-rework worker.

The one lesson we keep re-learning: agents must not act on ambiguous owner
input. When the owner clicks 'Needs rework' but leaves notes/tags/wins
empty, the correct behaviour is to BOUNCE the card back with a clarifying
note — NOT invent changes and NOT burn the paid deep-brain guessing.
"""
from __future__ import annotations

import json
from pathlib import Path

from carshorts.agents.rework import _feedback_is_empty, run


def test_feedback_is_empty_detects_the_empty_case() -> None:
    assert _feedback_is_empty({"slug": "x", "verdict": "rework", "rating": 4,
                               "beat_tags": {}, "beat_wins": {}, "notes": ""})
    assert _feedback_is_empty({"notes": "   ", "beat_tags": {}, "beat_wins": {}})


def test_feedback_is_empty_rejects_any_signal() -> None:
    assert not _feedback_is_empty({"notes": "remove music"})
    assert not _feedback_is_empty({"beat_tags": {"0": ["weak hook"]}})
    assert not _feedback_is_empty({"beat_wins": {"3": ["peak"]}})


def test_empty_rework_bounces_without_calling_llm_or_mechanic(
        tmp_path: Path, monkeypatch) -> None:
    """No LLM. No render. No mechanic. Card flips to awaiting_approval
    with a note asking the owner to be specific."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "queue").mkdir(parents=True)
    (tmp_path / "data" / "feedback").mkdir(parents=True)
    (tmp_path / "data" / "queue" / "creta.json").write_text(json.dumps({
        "car": "Hyundai Creta", "slug": "creta", "script": "s.json",
        "spec": "sp.json", "draft": "d.mp4", "status": "reworking"}))
    (tmp_path / "data" / "feedback" / "creta-20260722-000000.json").write_text(
        json.dumps({"slug": "creta", "verdict": "rework", "rating": 4,
                    "beat_tags": {}, "beat_wins": {}, "notes": ""}))

    def _boom(*_a, **_k):
        raise AssertionError("empty feedback must NOT invoke the LLM")
    monkeypatch.setattr("carshorts.agents.rework.make_llm", _boom)

    run("creta")

    card = json.loads((tmp_path / "data" / "queue" / "creta.json").read_text())
    assert card["status"] == "awaiting_approval"
    assert "empty" in card["note"].lower()
    assert "Tag" in card["note"] or "note" in card["note"]
