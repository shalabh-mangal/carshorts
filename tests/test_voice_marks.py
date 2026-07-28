"""Phrase-sync marks for open voice engines (Chatterbox/Kokoro don't emit word
timestamps natively). The proportional fallback must always yield monotonic,
in-range, per-word marks so cut placement never crashes and stays plausible."""
from carshorts.adapters.tts import _proportional_marks


def test_marks_one_per_word_monotonic_in_range():
    text = "The 2026 Brezza is back, and this time it packs a turbo."
    dur = 10.0
    marks = _proportional_marks(text, dur)
    assert len(marks) == len(text.split())
    times = [m["t"] for m in marks]
    assert times == sorted(times)          # monotonic non-decreasing
    assert times[0] == 0.0                 # first word starts at 0
    assert all(0.0 <= t < dur for t in times)


def test_marks_strip_punctuation_keep_word():
    marks = _proportional_marks("back, turbo!", 4.0)
    assert [m["w"] for m in marks] == ["back", "turbo"]


def test_marks_longer_words_advance_more():
    # a very long word should consume more of the timeline than a short one
    marks = _proportional_marks("a superlongwordhere b", 12.0)
    gap_after_long = marks[2]["t"] - marks[1]["t"]
    gap_after_short = marks[1]["t"] - marks[0]["t"]
    assert gap_after_long > gap_after_short


def test_marks_empty_text():
    assert _proportional_marks("", 5.0) == []


def test_marks_devanagari_hindi():
    # Hinglish/Hindi must not crash the fallback (no ASCII assumptions)
    marks = _proportional_marks("नई ब्रेज़ा turbo के साथ", 6.0)
    assert len(marks) == 5
    assert [m["t"] for m in marks] == sorted(m["t"] for m in marks)
