"""Offline tests for the experiment ledger + significance gate.

Two things must hold. First the statistics have to be REAL — the t-distribution
p-value is implemented here rather than pulled from scipy, so it is checked
against textbook critical values. Second, and more importantly, the gate must
DEFAULT TO REFUSING: its whole purpose is to stop a lucky video teaching the
writer a superstition it then follows forever.
"""
import pytest

from carshorts.intel.experiments import (
    evaluate,
    may_become_lesson,
    t_two_tailed_p,
    welch,
)


# --- the statistics are real ------------------------------------------------
def test_t_pvalue_matches_textbook_critical_values():
    # two-tailed 0.05 critical values: t(4)=2.776, t(10)=2.228, t(30)=2.042
    assert t_two_tailed_p(2.776, 4) == pytest.approx(0.05, abs=0.002)
    assert t_two_tailed_p(2.228, 10) == pytest.approx(0.05, abs=0.002)
    assert t_two_tailed_p(2.042, 30) == pytest.approx(0.05, abs=0.002)


def test_t_pvalue_of_zero_is_one():
    assert t_two_tailed_p(0.0, 10) == pytest.approx(1.0, abs=1e-9)


def test_welch_detects_a_clear_difference():
    r = welch([10, 11, 9, 10], [40, 41, 39, 40])
    assert r["diff"] == pytest.approx(30.0, abs=0.01)
    assert r["p"] < 0.001


def test_welch_on_identical_arms_finds_nothing():
    r = welch([10, 11, 9, 10], [10, 11, 9, 10])
    assert r["diff"] == pytest.approx(0.0, abs=1e-9)
    assert r["p"] > 0.9


# --- the gate defaults to refusing -----------------------------------------
def test_too_few_samples_is_insufficient_even_with_a_huge_effect():
    """The failure mode this whole module exists to prevent: two videos, a
    massive apparent effect, and a confident wrong lesson."""
    v = evaluate([10.0], [90.0], min_samples=3)
    assert v["status"] == "insufficient"
    assert not may_become_lesson(v)


def test_noise_is_reported_as_no_effect():
    v = evaluate([40, 42, 41, 43], [41, 40, 42, 42], min_samples=3)
    assert v["status"] == "no_effect"
    assert not may_become_lesson(v)


def test_clear_improvement_is_supported():
    v = evaluate([40, 41, 39, 40], [60, 61, 59, 60], min_samples=3)
    assert v["status"] == "supported"
    assert may_become_lesson(v)


def test_clear_regression_is_refuted_and_still_teaches():
    # a disproved hypothesis is knowledge too — it must be allowed to teach
    v = evaluate([60, 61, 59, 60], [40, 41, 39, 40], min_samples=3)
    assert v["status"] == "refuted"
    assert may_become_lesson(v)


def test_min_effect_blocks_a_statistically_real_but_trivial_difference():
    # tight variance makes a 1-point difference "significant"; it is not useful
    v = evaluate([40.0, 40.1, 39.9, 40.0], [41.0, 41.1, 40.9, 41.0],
                 min_samples=3, min_effect=5.0)
    assert v["status"] == "no_effect"
    assert not may_become_lesson(v)


# --- ledger behaviour -------------------------------------------------------
def test_a_video_cannot_serve_both_arms(tmp_path, monkeypatch):
    import carshorts.intel.experiments as ex
    monkeypatch.setattr(ex, "LEDGER", tmp_path / "experiments.json")
    ex.new_experiment("h", "length_s", "avg_view_pct", "58", "35")
    ex.assign("exp-001", "control", "VID1")
    with pytest.raises(ValueError):
        ex.assign("exp-001", "treatment", "VID1")


def test_assignment_is_idempotent(tmp_path, monkeypatch):
    import carshorts.intel.experiments as ex
    monkeypatch.setattr(ex, "LEDGER", tmp_path / "experiments.json")
    ex.new_experiment("h", "length_s", "avg_view_pct", "58", "35")
    ex.assign("exp-001", "control", "VID1")
    exp = ex.assign("exp-001", "control", "VID1")
    assert exp["arms"]["control"] == ["VID1"]


def test_videos_below_the_views_floor_are_excluded(tmp_path, monkeypatch):
    """A metric computed on a handful of views is noise. Our real 42.2% came
    from 7 processed views — exactly what this floor exists to reject."""
    import carshorts.intel.experiments as ex
    monkeypatch.setattr(ex, "LEDGER", tmp_path / "experiments.json")
    recipes = tmp_path / "recipes"
    recipes.mkdir()
    monkeypatch.setattr(ex, "RECIPES", recipes)
    import json as _json
    (recipes / "a.json").write_text(_json.dumps(
        {"video_id": "LOW", "metrics": {"avg_view_pct": 42.2, "views": 7}}), encoding="utf-8")
    (recipes / "b.json").write_text(_json.dumps(
        {"video_id": "OK", "metrics": {"avg_view_pct": 55.0, "views": 900}}), encoding="utf-8")

    values, skipped = ex._metric_values(["LOW", "OK"], "avg_view_pct", min_views=500)
    assert values == [55.0]
    assert any("LOW" in s for s in skipped)
