"""Tiered vision blocking (false-positive tightening): plates/watermarks block on a
single frame; wrong_vehicle_type must be corroborated across >=2 frames of the SAME
clip, so one stray background vehicle can't quarantine an otherwise on-subject clip.
Motivated by the Tata Sierra sunroof clip: a helicopter glimpsed once read as
'wrong_vehicle_type' and pulled the whole clip."""
from carshorts.quality import vqa


def _f(asset, *issues, t=1.0):
    return {"t": t, "asset": asset, "issues": list(issues)}


def test_plate_blocks_on_a_single_frame():
    fails = [_f("clip.mp4", "readable_plate")]
    assert vqa.blocking_fails(fails) == fails          # hard, never softened


def test_watermark_blocks_on_a_single_frame():
    fails = [_f("clip.mp4", "watermark_or_logo_overlay")]
    assert len(vqa.blocking_fails(fails)) == 1


def test_lone_wrong_vehicle_is_advisory_not_blocking():
    # one frame of a clip sees another vehicle -> do NOT quarantine the clip
    fails = [_f("sierra_sunroof.mp4", "wrong_vehicle_type")]
    assert vqa.blocking_fails(fails) == []


def test_corroborated_wrong_vehicle_blocks():
    # the wrong car shows across the clip -> genuinely wrong, block it
    fails = [_f("rival.mp4", "wrong_vehicle_type", t=1.0),
             _f("rival.mp4", "wrong_vehicle_type", t=3.0)]
    assert len(vqa.blocking_fails(fails)) == 2


def test_corroboration_is_per_clip_not_global():
    # two DIFFERENT clips each flagged once -> neither corroborated -> neither blocks
    fails = [_f("a.mp4", "wrong_vehicle_type"), _f("b.mp4", "wrong_vehicle_type")]
    assert vqa.blocking_fails(fails) == []


def test_hard_issue_still_blocks_even_when_wrong_vehicle_is_lone():
    # a lone frame with BOTH a plate and a wrong-vehicle flag still blocks (the plate)
    fails = [_f("clip.mp4", "readable_plate", "wrong_vehicle_type")]
    assert len(vqa.blocking_fails(fails)) == 1


def test_dark_or_blurry_and_clutter_never_block():
    fails = [_f("clip.mp4", "too_dark_or_blurry"), _f("clip.mp4", "clutter")]
    assert vqa.blocking_fails(fails) == []
