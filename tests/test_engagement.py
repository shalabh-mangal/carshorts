"""Offline tests for the engagement engine.

The subtle rule being locked in: a video with comments DISABLED reports no
commentCount at all. That must stay `None` (unknown), never collapse to 0 —
otherwise a disabled comment section would masquerade as an audience that saw
the CTA and chose not to reply, and we would "learn" from a signal that was
never possible.
"""
from carshorts.engagement import rates, summarize_engagement


def _v(views, likes, comments):
    return {"views": views, "likes": likes, "comments": comments}


def test_rates_are_percent_of_views():
    r = rates(_v(1000, 20, 5))
    assert r["like_rate"] == 2.0
    assert r["comment_rate"] == 0.5


def test_zero_views_is_undefined_not_zero():
    r = rates(_v(0, 0, 0))
    assert r["like_rate"] is None and r["comment_rate"] is None


def test_comments_disabled_stays_unknown():
    r = rates(_v(1000, 10, None))
    assert r["like_rate"] == 1.0
    assert r["comment_rate"] is None      # NOT 0.0


def test_zero_comments_is_a_real_signal():
    # genuinely zero comments (feature enabled) must be measured as 0, not None
    r = rates(_v(1000, 10, 0))
    assert r["comment_rate"] == 0.0


def test_summary_uses_medians_not_means():
    # one viral outlier must not drag the channel's typical rate upward
    vids = [_v(1000, 10, 1), _v(1000, 10, 1), _v(1000, 900, 1)]
    s = summarize_engagement(vids)
    assert s["median_like_rate"] == 1.0        # median, not the 30.3% mean


def test_views_floor_filters_noisy_small_videos():
    # 1 like on 3 views is 33% — statistical nonsense that must be excluded
    vids = [_v(3, 1, 0), _v(5000, 50, 5)]
    s = summarize_engagement(vids, min_views=1000)
    assert s["videos"] == 1
    assert s["median_like_rate"] == 1.0


def test_empty_input_is_safe():
    assert summarize_engagement([])["videos"] == 0
    assert summarize_engagement([_v(10, 1, 0)], min_views=1000)["videos"] == 0


def test_disabled_comments_are_counted_separately():
    vids = [_v(2000, 20, None), _v(2000, 20, 4)]
    s = summarize_engagement(vids)
    assert s["comments_disabled"] == 1
    assert s["median_comment_rate"] == 0.2     # only the one that had comments
