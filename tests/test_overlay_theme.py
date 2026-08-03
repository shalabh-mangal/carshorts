"""Offline tests for the premium overlay themes (A "luxe" / B "frost").

Covers the theme registry, the A/B auto-alternation used to balance the owner's
experiment, and the count-up card bugfix (a unit label crammed into the number
line used to clip off both frame edges)."""
import tempfile

from PIL import Image

from carshorts.adapters import renderer as R
from carshorts.core import paths
from carshorts.rendering.produce import _resolve_overlay_theme


def test_theme_registry_and_default():
    assert R.get_theme("luxe") is R.THEME_LUXE
    assert R.get_theme("frost") is R.THEME_FROST
    assert R.get_theme(None) is R.THEME_LUXE          # default = owner's pick
    assert R.get_theme("nonsense") is R.THEME_LUXE     # unknown falls back safely


def test_themes_differ_where_it_matters():
    # A is boxless + thin; B is a smoked-glass panel + heavier weight.
    assert R.THEME_LUXE.container == "none"
    assert R.THEME_FROST.container == "panel"
    assert R.THEME_LUXE.value_w != R.THEME_FROST.value_w
    # the retired tech-cyan is not the accent of either premium theme
    assert R.THEME_LUXE.accent != R.ACCENT_CYAN
    assert R.THEME_FROST.accent != R.ACCENT_CYAN


def test_auto_alternates_for_ab_test(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "DATA", tmp_path)
    first = _resolve_overlay_theme("auto")
    second = _resolve_overlay_theme("auto")
    third = _resolve_overlay_theme("auto")
    assert first == "luxe"              # first render is the owner's pick
    assert {first, second} == {"luxe", "frost"}   # then it flips
    assert third == first              # ...and flips back


def test_explicit_theme_passes_through(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "DATA", tmp_path)
    assert _resolve_overlay_theme("frost") == "frost"
    assert _resolve_overlay_theme("luxe") == "luxe"


def test_countup_label_split_never_clips():
    # BUGFIX: "₹11.49L · EX-SHOWROOM" used to render the whole string as the giant
    # count-up number and clip off both edges. The label must split out and the
    # value must fit inside the 1080px canvas for BOTH themes.
    td = tempfile.mkdtemp()
    for theme in (R.THEME_LUXE, R.THEME_FROST):
        frames = R._countup_frames("₹11.49L · EX-SHOWROOM", "", td,
                                   f"card_{theme.name}", theme=theme)
        assert frames, "count-up produced no frames"
        widest = max(Image.open(f).width for f in frames)
        assert widest <= 1080, f"{theme.name} card clips the frame ({widest}px)"


def test_chip_renders_for_both_themes():
    td = tempfile.mkdtemp()
    for theme in (R.THEME_LUXE, R.THEME_FROST):
        png = R._overlay_png("160 PS TURBO", 96, f"{td}/chip_{theme.name}.png",
                             theme=theme, kind="number")
        assert Image.open(png).width <= 1080
