"""Offline tests for the overlay-overlap self-check (_pop_overlaps).

The owner's defect: two text overlays on screen at once. The rail karaoke prevents
rail collisions by design; this guard catches any regression + top-slot
(reaction/card) collisions, and feeds an OVERLAP quality warning that QA fails on.
LSS is a cumulative icon strip and must never count as an overlap."""
from carshorts.rendering.produce import _pop_overlaps


def _pop(start, dur, text, kind):
    return (start, dur, text, kind, "")


def test_sequential_rail_pops_do_not_overlap():
    pops = [_pop(0.0, 1.0, "160 PS TURBO", "number"),
            _pop(1.1, 1.0, "PANORAMIC ROOF", "word")]
    assert _pop_overlaps(pops) == []


def test_overlapping_rail_pops_are_flagged():
    pops = [_pop(0.0, 1.2, "160 PS TURBO", "number"),
            _pop(0.5, 1.0, "PANORAMIC ROOF", "word")]     # starts before the first ends
    hits = _pop_overlaps(pops)
    assert len(hits) == 1
    assert hits[0][0] == "160 PS TURBO" and hits[0][2] == "rail"


def test_different_slots_never_collide():
    # a rail number and a top reaction can share the same time — different slots
    pops = [_pop(0.0, 1.5, "160 PS TURBO", "number"),
            _pop(0.2, 1.1, "STEAL!", "reaction")]
    assert _pop_overlaps(pops) == []


def test_lss_strip_is_not_an_overlap():
    # LIKE/SHARE/SUBSCRIBE build cumulatively on screen — never flagged
    pops = [_pop(0.0, 1.0, "LIKE", "lss"),
            _pop(0.3, 1.0, "SHARE", "lss"),
            _pop(0.6, 1.0, "SUBSCRIBE", "lss")]
    assert _pop_overlaps(pops) == []
