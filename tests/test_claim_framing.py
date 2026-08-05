"""Low-confidence (pre-launch/claimed) specs must be flagged so the writer
attributes them instead of stating them as fact — the accuracy discipline we
apply by hand (e.g. an unreleased car with no official spec page)."""
from carshorts.core.models import Spec, SpecSheet
from carshorts.writing.prompts import render_spec_sheet


def _sheet(conf):
    return SpecSheet(subject="X", specs=[
        Spec(name="range", value="1000 km", source_url="https://x", source_sentence="claimed", confidence=conf),
        Spec(name="power", value="195 hp", source_url="https://x", source_sentence="confirmed", confidence=0.95),
    ])


def test_low_confidence_specs_marked_claimed():
    out = render_spec_sheet(_sheet(0.5))
    assert "[CLAIMED" in out and "ACCURACY RULE" in out
    # only the low-confidence spec gets the inline tag (unique '[CLAIMED —' marker;
    # the note also mentions '[CLAIMED]' so match the tag form specifically)
    assert out.count("[CLAIMED —") == 1


def test_all_confirmed_no_claim_markers():
    out = render_spec_sheet(_sheet(0.9))
    assert "[CLAIMED" not in out and "ACCURACY RULE" not in out
