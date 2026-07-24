"""Deterministic opening-still selection.

Frame 1 IS the thumbnail on a Short, and it used to be whatever the LLM
phrase-matcher returned that run — two renders of the same Creta script opened
on different photographs. Selection must now be a pure function of the pool and
the rival baseline, so the same inputs always yield the same opener.
"""
from PIL import Image

from carshorts.firstframe import choose_opening_still, rank_opening_stills, score_still

BASE = {"brightness": 117.44, "contrast": 63.45, "colorfulness": 43.6,
        "edge_density": 18.24}


def _img(tmp_path, name, rgb, noisy=False):
    p = tmp_path / name
    img = Image.new("RGB", (120, 200), rgb)
    if noisy:  # add structure so edge_density is non-trivial
        px = img.load()
        for y in range(0, 200, 3):
            for x in range(120):
                px[x, y] = (255 - rgb[0], 255 - rgb[1], 255 - rgb[2])
    img.save(p)
    return p


def test_score_rewards_reaching_the_norm_not_exceeding_it():
    at_norm = score_still(BASE, BASE)
    brighter = score_still({**BASE, "brightness": BASE["brightness"] * 3}, BASE)
    assert at_norm == 1.0
    assert brighter == 1.0          # exceeding earns no extra credit


def test_score_punishes_a_dark_flat_frame():
    dark = score_still({"brightness": 20, "contrast": 10, "colorfulness": 5,
                        "edge_density": 2}, BASE)
    assert dark < 0.3


def test_edge_density_is_scored_symmetrically():
    """Both a barren frame and a cluttered one fail to stop a scroll."""
    barren = score_still({**BASE, "edge_density": BASE["edge_density"] / 4}, BASE)
    cluttered = score_still({**BASE, "edge_density": BASE["edge_density"] * 4}, BASE)
    assert barren < 1.0 and cluttered < 1.0
    assert abs(barren - cluttered) < 0.02      # penalised about equally


def test_empty_baseline_scores_zero_rather_than_crashing():
    assert score_still(BASE, {}) == 0.0


def test_chooses_the_brighter_richer_still(tmp_path):
    dull = _img(tmp_path, "a_dull.png", (18, 18, 20), noisy=True)
    vivid = _img(tmp_path, "b_vivid.png", (210, 120, 40), noisy=True)
    got = choose_opening_still([dull, vivid], BASE)
    assert got["path"] == str(vivid)


def test_selection_is_deterministic(tmp_path):
    a = _img(tmp_path, "a.png", (200, 110, 40), noisy=True)
    b = _img(tmp_path, "b.png", (205, 115, 45), noisy=True)
    first = choose_opening_still([a, b], BASE)["path"]
    for _ in range(4):
        assert choose_opening_still([b, a], BASE)["path"] == first  # order-independent


def test_unreadable_candidates_are_skipped(tmp_path):
    good = _img(tmp_path, "good.png", (200, 120, 60), noisy=True)
    bad = tmp_path / "broken.png"
    bad.write_text("not an image", encoding="utf-8")
    got = choose_opening_still([bad, good], BASE)
    assert got is not None and got["path"] == str(good)


def test_no_candidates_returns_none(tmp_path):
    assert choose_opening_still([], BASE) is None


def test_rank_returns_all_candidates_best_first(tmp_path):
    # used by vet-on-use to walk from the top down past any blocked image
    dull = _img(tmp_path, "dull.png", (18, 18, 20), noisy=True)
    vivid = _img(tmp_path, "vivid.png", (210, 120, 40), noisy=True)
    ranked = rank_opening_stills([dull, vivid], BASE)
    assert [p for _, p, _ in ranked] == [str(vivid), str(dull)]
    assert ranked[0][0] >= ranked[1][0]


def test_rank_lets_caller_skip_a_blocked_top_pick(tmp_path):
    """The whole point: if the best-scoring still is veto'd (e.g. a plate the
    scorer can't see), the next-best clean one is chosen instead."""
    best = _img(tmp_path, "best.png", (215, 125, 45), noisy=True)
    second = _img(tmp_path, "second.png", (205, 118, 42), noisy=True)
    ranked = rank_opening_stills([best, second], BASE)
    blocked = {str(best)}
    pick = next(p for _, p, _ in ranked if p not in blocked)
    assert pick == str(second)
