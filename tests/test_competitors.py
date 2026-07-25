"""Offline tests for competitor intel (no network).

The engine's value is that it compares SHAPE, not scale — so the aggregation has
to be right. Rival retention/CTR are private and deliberately absent; nothing
here should imply we can see them.
"""
import datetime

from carshorts.intel.competitors import iso_duration_seconds, summarize, title_features


def _vid(title, views, dur, day):
    return {"id": "x", "title": title, "views": views, "likes": 0, "duration_s": dur,
            "published": datetime.datetime(2026, 7, day)}


def test_iso_duration_parsing():
    assert iso_duration_seconds("PT46S") == 46
    assert iso_duration_seconds("PT1M3S") == 63
    assert iso_duration_seconds("PT1H2M3S") == 3723
    assert iso_duration_seconds("") == 0
    assert iso_duration_seconds("garbage") == 0


def test_title_features():
    f = title_features("Tata Nexon: 0-100 in 9.9s… BEST SUV?")
    assert f["is_question"] and f["has_number"] and f["has_colon"]
    assert f["caps_words"] >= 1
    assert f["words"] == len(["Tata", "Nexon:", "0-100", "in", "9.9s…", "BEST", "SUV?"])


def test_title_features_plain():
    f = title_features("A quiet little drive")
    assert not f["is_question"] and not f["has_number"] and not f["has_colon"]


def test_summarize_shape_metrics():
    vids = [
        _vid("Short one 5 tips?", 100, 45, 1),
        _vid("Short two", 300, 55, 8),        # 7 days later
        _vid("A long review of the car", 50, 600, 8),
    ]
    s = summarize(vids)
    assert s["videos_sampled"] == 3
    assert s["median_views"] == 100
    assert s["max_views"] == 300
    assert s["short_form_share_pct"] == 67          # 2 of 3 under 180s
    assert s["median_shortform_duration_s"] == 50   # median of 45 and 55
    assert s["uploads_per_week"] == 3.0             # 3 uploads across a 7-day span
    assert s["title_question_pct"] == 33
    assert s["title_number_pct"] == 33


def test_summarize_handles_empty():
    assert summarize([]) == {}


def test_summarize_single_video_has_no_cadence():
    # one upload cannot imply a rate — must not fabricate one
    s = summarize([_vid("Only", 10, 30, 1)])
    assert s["uploads_per_week"] is None
    assert s["videos_sampled"] == 1


def test_long_form_only_channel_reports_no_shortform_length():
    s = summarize([_vid("Long", 10, 900, 1), _vid("Longer", 20, 1200, 2)])
    assert s["short_form_share_pct"] == 0
    assert s["median_shortform_duration_s"] is None
