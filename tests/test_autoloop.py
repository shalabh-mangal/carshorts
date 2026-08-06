"""The self-improving loop: QA/critique -> auto-fix -> re-render, until ship or
owner. Decision core + vision quarantine are pure/fs; the full loop runs with an
injected render that reflects the fix (quarantine a bad clip -> next render clean)."""
import json

from carshorts.agents import autoloop
from carshorts.core import paths


# --- decision brain -------------------------------------------------------
def test_ship_when_clean_and_critic_passes():
    assert autoloop.next_action(vision_blocked=False, footage_qa_red=False,
                                critique_score=8, attempt=0) == "ship"


def test_vision_block_is_fixed_first():
    assert autoloop.next_action(vision_blocked=True, footage_qa_red=False,
                                critique_score=9, attempt=0) == "fix_vision"


def test_weak_critic_triggers_script_revise():
    assert autoloop.next_action(vision_blocked=False, footage_qa_red=False,
                                critique_score=6, attempt=0) == "fix_script"


def test_footage_red_surfaces_to_owner():
    # a LOOP/REPEAT red is a footage gap we can't invent past
    assert autoloop.next_action(vision_blocked=False, footage_qa_red=True,
                                critique_score=9, attempt=0) == "surface"


def test_out_of_attempts_surfaces():
    assert autoloop.next_action(vision_blocked=True, footage_qa_red=False,
                                critique_score=3, attempt=2, max_iter=2) == "surface"


# --- vision quarantine ----------------------------------------------------
def test_quarantine_moves_blocked_clip(tmp_path, monkeypatch):
    car = tmp_path / "cars" / "x"
    (car / "own").mkdir(parents=True)
    (car / "own" / "bad.mp4").write_text("x")
    (car / "own" / "good.mp4").write_text("x")
    monkeypatch.setattr(paths, "car_dir", lambda slug: tmp_path / "cars" / slug)
    vqp = tmp_path / "v.vqa.json"
    vqp.write_text(json.dumps({"blocking": 1, "blocking_detail": [
        {"t": 1.0, "asset": "own/bad.mp4", "issues": ["readable_plate"]}]}))
    moved = autoloop.quarantine_flagged("x", vqp)
    assert moved == ["bad.mp4"]
    assert not (car / "own" / "bad.mp4").exists()
    assert (car / "own" / "_rejected" / "bad.mp4").exists()
    assert (car / "own" / "good.mp4").exists()          # the clean clip stays


# --- full loop: vision block -> quarantine -> clean -> ship ---------------
def test_auto_improve_quarantines_then_ships(tmp_path, monkeypatch):
    queue = tmp_path / "queue"; queue.mkdir()
    car = tmp_path / "cars" / "x"; (car / "own").mkdir(parents=True)
    (car / "own" / "bad.mp4").write_text("x")
    monkeypatch.setattr(paths, "QUEUE", queue)
    monkeypatch.setattr(paths, "car_dir", lambda slug: tmp_path / "cars" / slug)
    out = tmp_path / "out" / "x_draft.mp4"; out.parent.mkdir()

    def render_fn():
        # once the bad clip is quarantined, the render comes back vision-clean
        bad_present = (car / "own" / "bad.mp4").exists()
        out.with_suffix(".manifest.json").write_text(json.dumps({"quality_warnings": []}))
        out.with_suffix(".vqa.json").write_text(json.dumps(
            {"blocking": 1, "blocking_detail": [{"asset": "own/bad.mp4", "issues": ["readable_plate"]}]}
            if bad_present else {"blocking": 0, "blocking_detail": []}))
        (queue / "x.json").write_text(json.dumps({"critique": {"score": 6 if bad_present else 9}}))

    revised = {"n": 0}
    result = autoloop.auto_improve("x", str(out), render_fn, lambda _s: revised.__setitem__("n", revised["n"] + 1))
    assert result == "shipped"
    assert (car / "own" / "_rejected" / "bad.mp4").exists()   # the plated clip was pulled
    assert revised["n"] == 0                                   # vision fix, no script revise needed
