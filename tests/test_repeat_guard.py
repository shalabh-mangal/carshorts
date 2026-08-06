"""The owner's #1 rule: never reuse a video clip. The LOOP check catches a clip
playing past its own length; this guard catches the SAME clip used in two
different cuts (a thin pool forces this), which LOOP misses."""
from carshorts.rendering.produce import _repeated_video_clips


def _sec(*assets):
    return {"cuts": [{"asset": a} for a in assets]}


def test_flags_clip_reused_across_cuts():
    sections = [
        _sec("own/hero.mp4", "own/road.mp4"),
        _sec("own/dash.mp4"),
        _sec("own/hero.mp4"),          # hero.mp4 reused in a second cut
    ]
    rep = _repeated_video_clips(sections)
    assert rep == {"hero.mp4": 2}


def test_distinct_clips_are_clean():
    sections = [_sec("a.mp4", "b.mp4"), _sec("c.mp4"), _sec("d.mp4")]
    assert _repeated_video_clips(sections) == {}


def test_stills_may_repeat():
    # images legitimately fill multiple gaps — only VIDEO reuse is a violation
    sections = [_sec("still.jpg"), _sec("still.jpg"), _sec("clip.mp4")]
    assert _repeated_video_clips(sections) == {}


# --- stock-leak guard: own footage present -> no generic stock unless forced ---
from carshorts.rendering.produce import _stock_default


def test_stock_off_by_default_when_owner_has_clips():
    assert _stock_default(None, own_present=True) is False   # never leak stock over own
    assert _stock_default(None, own_present=False) is True   # no own clips -> stock ok


def test_explicit_stock_flag_wins():
    assert _stock_default(True, own_present=True) is True     # --stock forces it
    assert _stock_default(False, own_present=False) is False  # --no-stock forces off
