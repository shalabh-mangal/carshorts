"""Offline tests for overlay anchor-timing (produce._exact_span).

Overlays are timed to the SPOKEN word marks, which come from normalize_for_speech
(so '13-speaker' is voiced '13 speaker'). The anchor must be normalized the same
way or a hyphenated/compound anchor never matches and its overlay is dropped
(the '13-SPKR JBL' / 'PANORAMIC ROOF' drops the analyst flagged)."""
import json

from carshorts.rendering.produce import _exact_span


def _marks(tmp_path, words):
    """Write a TTS word-marks file: evenly spaced {'w','t'} entries."""
    p = tmp_path / "m.json"
    p.write_text(json.dumps([{"w": w, "t": round(0.4 * i, 2)} for i, w in enumerate(words)]))
    return str(p)


def test_hyphenated_anchor_matches_spoken_split(tmp_path):
    # voiced as "13 speaker JBL"; anchor written "13-speaker JBL" must still match
    mf = _marks(tmp_path, ["13", "speaker", "JBL", "sound"])
    assert _exact_span("13-speaker JBL", mf, (0.0, 0.0)) is not None


def test_prefix_fallback_fires_on_spoken_words(tmp_path):
    # line says "panoramic sunroof"; anchor "panoramic roof" falls back to
    # "panoramic" instead of vanishing
    mf = _marks(tmp_path, ["panoramic", "sunroof", "today"])
    span = _exact_span("panoramic roof", mf, (0.0, 0.0))
    assert span is not None and span[0] < 0.4        # fires at 'panoramic' (t=0)


def test_absent_anchor_still_returns_none(tmp_path):
    mf = _marks(tmp_path, ["ventilated", "seats"])
    assert _exact_span("wireless charging", mf, (0.0, 0.0)) is None


def test_no_marks_file_returns_none():
    assert _exact_span("anything", None, (0.0, 0.0)) is None
