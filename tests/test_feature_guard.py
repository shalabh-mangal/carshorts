"""Offline tests for the deterministic feature-guard.

The number-guard only sees digits, so a fabricated EQUIPMENT claim ("cruise
control", "sunroof") carries no number and sails through — the exact hole that
let "cruise control" into a Tata Punch draft. This guard closes it.
"""
from carshorts.core.models import Script, ScriptSegment, Spec, SpecSheet
from carshorts.writing.draft import unsourced_features_check

SHEET = SpecSheet(
    subject="Tata Punch",
    specs=[
        Spec(name="safety_rating", value="5-star Global NCAP",
             source_url="https://en.wikipedia.org/wiki/Tata_Punch",
             source_sentence="The Tata Punch scored 5 stars for adult occupant protection."),
        Spec(name="boot_space", value="366 litres",
             source_url="https://en.wikipedia.org/wiki/Tata_Punch",
             source_sentence="The top variant adds a sunroof; boot space is 366 litres."),
    ],
)


def _script(*texts: str) -> Script:
    return Script(subject="Tata Punch",
                  segments=[ScriptSegment(role="spec", text=t) for t in texts])


def test_flags_fabricated_feature():
    problems = unsourced_features_check(_script("It even gets cruise control!"), SHEET)
    assert any("cruise control" in p for p in problems)


def test_does_not_flag_sourced_feature():
    # "sunroof" appears in a spec's source sentence -> sourced, must not flag.
    problems = unsourced_features_check(_script("And yes, it finally has a sunroof."), SHEET)
    assert problems == []


def test_clean_script_no_flags():
    problems = unsourced_features_check(_script("Five-star safety and a big boot."), SHEET)
    assert problems == []
