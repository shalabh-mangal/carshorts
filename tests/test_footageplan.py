"""Footage cockpit (Step 4): coverage + provenance + shopping list.

The core math is pure (`plan_from_names`); `assess` is exercised over a temp pool
so the filesystem read, provenance merge, and _rejected/ exclusion are covered too.
"""
from carshorts.core import paths
from carshorts.sourcing import footageplan as fp


# --- angle inference ------------------------------------------------------
def test_angle_of_maps_owner_and_ingest_naming():
    assert fp.angle_of("sierra_hero.mp4") == "front"
    assert fp.angle_of("sierra_dash.mp4") == "interior"
    assert fp.angle_of("sierra_sunroof.mp4") == "interior"
    assert fp.angle_of("sierra_sand.mp4") == "action"
    assert fp.angle_of("pool_03_rear2.mp4") == "rear"
    assert fp.angle_of("pool_07_side.mp4") == "side"
    assert fp.angle_of("mystery_clip.mp4") == "other"


# --- coverage math --------------------------------------------------------
def test_shortfall_and_missing_angles():
    # 4 clips, all action/interior -> short of 10 cuts AND missing front/side/rear
    plan = fp.plan_from_names(
        ["a_sand.mp4", "b_sea.mp4", "c_dash.mp4", "d_sunroof.mp4"], [],
        target_cuts=10)
    assert plan["clean_video"] == 4
    assert plan["shortfall_cuts"] == 6
    assert set(plan["missing_essential"]) == {"front", "side", "rear"}
    assert plan["ready"] is False


def test_ready_when_enough_and_all_angles():
    names = ["front1.mp4", "side1.mp4", "rear1.mp4", "interior1.mp4",
             "action1.mp4", "front2.mp4", "side2.mp4", "rear2.mp4",
             "interior2.mp4", "action2.mp4"]
    plan = fp.plan_from_names(names, [], target_cuts=10,
                             known_sources=set(names))
    assert plan["shortfall_cuts"] == 0
    assert plan["missing_essential"] == []
    assert plan["unverified_source"] == []
    assert plan["ready"] is True


def test_unverified_source_flagged():
    plan = fp.plan_from_names(
        ["front1.mp4", "side1.mp4"], [], target_cuts=2,
        known_sources={"front1.mp4"})
    assert plan["unverified_source"] == ["side1.mp4"]
    # shortfall met but provenance gap keeps the shopping list non-empty
    lines = " ".join(fp.shopping_list(plan))
    assert "cleared source" in lines.lower()


def test_shopping_list_ready_message():
    names = ["front1.mp4", "side1.mp4", "rear1.mp4", "interior1.mp4", "action1.mp4"]
    plan = fp.plan_from_names(names, [], target_cuts=5, known_sources=set(names))
    assert fp.shopping_list(plan) == [
        "Pool is render-ready: enough distinct clips, all essential "
        "angles covered, provenance recorded."]


# --- filesystem assess: real pool, _rejected excluded, provenance merged --
def test_assess_reads_pool_excludes_rejected(tmp_path, monkeypatch):
    car = tmp_path / "cars" / "x"
    (car / "own").mkdir(parents=True)
    (car / "images").mkdir()
    for n in ("front1.mp4", "side1.mp4"):
        (car / "own" / n).write_text("v")
    (car / "own" / "rear1.jpg").write_text("i")          # still in own/ counts as still
    (car / "images" / "x_front_0.jpg").write_text("i")
    # a quarantined clip must NOT count toward coverage
    (car / "own" / "_rejected").mkdir()
    (car / "own" / "_rejected" / "bad_plate.mp4").write_text("v")
    # provenance: only front1 is cleared
    (car / "footage_sources.json").write_text(
        '[{"file": "front1.mp4", "source": "owner shoot", "license": "owned"}]')
    monkeypatch.setattr(paths, "car_dir", lambda slug: tmp_path / "cars" / slug)

    plan = fp.assess("x", target_cuts=4)
    assert plan["clean_video"] == 2                       # bad_plate.mp4 excluded
    assert plan["stills"] == 2                            # own/rear1.jpg + images/*
    assert plan["unverified_source"] == ["side1.mp4"]     # front1 is cleared
    assert plan["shortfall_cuts"] == 2
