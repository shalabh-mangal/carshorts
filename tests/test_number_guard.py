"""Offline tests for the deterministic number-guard.

This is the model-independent backstop: it must flag a figure that appears in the
script but in no spec, and must NOT flag figures that are genuinely sourced. The
real case that motivated it: a 7B model wrote "₹12.99 lakh" for a car whose spec
sheet has no price, and the LLM fact-checker missed it.
"""
from carshorts.models import Script, ScriptSegment, Spec, SpecSheet
from carshorts.stages.pipeline import unsourced_numbers_check

SHEET = SpecSheet(
    subject="Tata Nexon",
    specs=[
        Spec(name="power", value="81 kW", source_url="https://en.wikipedia.org/wiki/Tata_Nexon",
             source_sentence="...diesel engine producing 81 kW (109 hp; 110 PS)..."),
        Spec(name="acceleration", value="9.9 seconds",
             source_url="https://en.wikipedia.org/wiki/Tata_Nexon",
             source_sentence="...245 N⋅m of torque and 0 - 100 under 9.9 seconds."),
    ],
)


def _script(*texts: str) -> Script:
    return Script(subject="Tata Nexon",
                  segments=[ScriptSegment(role="spec", text=t) for t in texts])


def test_flags_fabricated_price():
    problems = unsourced_numbers_check(_script("Only ₹12.99 lakh, bhai!"), SHEET)
    assert any("12.99" in p for p in problems)


def test_flags_fabricated_power():
    problems = unsourced_numbers_check(_script("A massive 180 bhp monster."), SHEET)
    assert any("180" in p for p in problems)


def test_does_not_flag_sourced_numbers():
    # 81 kW and 9.9 seconds are both in the sheet — must not be flagged.
    problems = unsourced_numbers_check(
        _script("81 kW of power.", "0 to 100 in 9.9 seconds."), SHEET)
    assert problems == []


def test_ignores_numbers_without_units():
    # A bare number (a count, a year) with no unit is not a spec claim.
    problems = unsourced_numbers_check(_script("The 2024 model, ranked number 1."), SHEET)
    assert problems == []
