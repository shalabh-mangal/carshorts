"""Offline tests for Angle Lab — the Script Studio learning loop.

Ranks script formats by performance from the render recipes and writes ONE
[angle-lab] learning (which the angle miner then reads as a prior). Must no-op on
a thin sample and never invent a lesson."""
import json

from carshorts.core import paths
from carshorts.intel import anglelab


def _recipe(tmp, name, fmt, views, ret=None):
    (tmp / f"{name}.json").write_text(json.dumps({
        "subject": name, "script_format": fmt,
        "metrics": {"views": views, "avg_view_pct": ret},
    }), encoding="utf-8")


def test_noop_without_enough_data(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "RECIPES", tmp_path)
    _recipe(tmp_path, "a", "vs", 3000)
    _recipe(tmp_path, "b", "spotlight", 1000)
    out = anglelab.summarize(min_videos=4)
    assert out["ready"] is False and out["videos"] == 2


def test_ranks_and_writes_learning(tmp_path, monkeypatch):
    rec = tmp_path / "recipes"
    rec.mkdir()
    learn = tmp_path / "learnings.json"
    learn.write_text(json.dumps({"craft_playbook": [], "data_learnings": []}), encoding="utf-8")
    monkeypatch.setattr(paths, "RECIPES", rec)
    monkeypatch.setattr(paths, "LEARNINGS", learn)
    _recipe(rec, "a", "vs", 3000, 55)
    _recipe(rec, "b", "vs", 3400, 60)
    _recipe(rec, "c", "spotlight", 1000, 40)
    _recipe(rec, "d", "spotlight", 1200, 45)

    out = anglelab.summarize(min_videos=4)
    assert out["ready"] is True
    assert out["stats"][0]["format"] == "vs"          # highest avg views ranks first
    dl = json.loads(learn.read_text(encoding="utf-8"))["data_learnings"]
    tagged = [x for x in dl if "[angle-lab]" in x]
    assert len(tagged) == 1 and "vs" in tagged[0]


def test_learning_is_idempotent(tmp_path, monkeypatch):
    rec = tmp_path / "recipes"
    rec.mkdir()
    learn = tmp_path / "learnings.json"
    learn.write_text(json.dumps({"craft_playbook": [], "data_learnings": []}), encoding="utf-8")
    monkeypatch.setattr(paths, "RECIPES", rec)
    monkeypatch.setattr(paths, "LEARNINGS", learn)
    for i in range(4):
        _recipe(rec, f"r{i}", "vs" if i < 2 else "spotlight", 3000 - i * 100, 50)
    anglelab.summarize(min_videos=4)
    anglelab.summarize(min_videos=4)                  # run twice — replaces, not appends
    dl = json.loads(learn.read_text(encoding="utf-8"))["data_learnings"]
    assert len([x for x in dl if "[angle-lab]" in x]) == 1
