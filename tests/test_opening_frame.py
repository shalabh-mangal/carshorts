"""The opening cut must not be darkened; every other cut must be.

On a Short frame 1 IS the thumbnail. Stills are blended 35% toward black so
white overlay text stays readable, but the opener carries no text yet (pops are
voice-synced and start later), so it paid that tax for nothing. Measured against
127 real rival Shorts thumbnails our openers ran 0.70x brightness / 0.71x
contrast / 0.59x colourfulness of the feed norm.

The loop-close tail flashes the SAME opening visual, so it has to match — a
darkened tail against an undarkened opener would show a visible seam exactly
where the Short loops.
"""
from PIL import Image

from carshorts.adapters.renderer import (
    DEFAULT_DARKEN,
    OPENING_DARKEN,
    MoviePyRenderer,
)
from carshorts.quality.firstframe import frame_stats


def _source(tmp_path):
    p = tmp_path / "src.png"
    Image.new("RGB", (1080, 1920), (200, 120, 60)).save(p)
    return str(p)


def test_opening_frame_is_not_darkened(tmp_path):
    r = MoviePyRenderer()
    src = _source(tmp_path)
    opener = frame_stats(r._prepare_background(src, None, darken=OPENING_DARKEN))
    normal = frame_stats(r._prepare_background(src, None, darken=DEFAULT_DARKEN))
    assert opener["brightness"] > normal["brightness"]


def test_default_darkening_is_still_applied(tmp_path):
    """Regression guard: the fix must not quietly remove darkening everywhere,
    which would hurt overlay legibility on every mid-video cut."""
    r = MoviePyRenderer()
    src = _source(tmp_path)
    raw = frame_stats(src)
    normal = frame_stats(r._prepare_background(src, None, darken=DEFAULT_DARKEN))
    assert normal["brightness"] < raw["brightness"] * 0.8


def test_undarkened_opener_recovers_the_source_brightness(tmp_path):
    # a 0.35 blend toward black multiplies luma by 0.65; removing it should
    # return essentially the original image
    r = MoviePyRenderer()
    src = _source(tmp_path)
    raw = frame_stats(src)
    opener = frame_stats(r._prepare_background(src, None, darken=OPENING_DARKEN))
    assert opener["brightness"] == raw["brightness"]


def test_darkening_scales_colourfulness_too(tmp_path):
    # the measured gap was not only brightness — colour was crushed as well
    r = MoviePyRenderer()
    src = _source(tmp_path)
    opener = frame_stats(r._prepare_background(src, None, darken=OPENING_DARKEN))
    normal = frame_stats(r._prepare_background(src, None, darken=DEFAULT_DARKEN))
    assert opener["colorfulness"] > normal["colorfulness"]
    assert opener["contrast"] >= normal["contrast"]
