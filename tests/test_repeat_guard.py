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
