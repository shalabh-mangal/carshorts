"""Offline tests for the deterministic spec extractor.

No network: we feed known article-style prose and assert the extractor lifts
values bound to their VERBATIM source sentence. This is the honesty gate the
whole harness depends on — if extraction ever paraphrases, the hallucination
number it produces would be measuring against a fabricated answer key.
"""
from carshorts.adapters.specsource import extract_specs

URL = "https://en.wikipedia.org/wiki/Example_Car"

ARTICLE = (
    "The Example Car is a compact SUV. "
    "The 2.0-litre turbo-petrol engine produces 172 bhp and 250 Nm of torque. "
    "Prices start at Rs 12.99 lakh ex-showroom. "
    "It can accelerate from 0 to 100 km/h in 8.2 seconds. "
    "The manufacturer claims a fuel economy of 18 kmpl. "
    "It has a top speed of 180 km/h."
)


def _by_name(specs):
    return {s.name: s for s in specs}


def test_extracts_expected_spec_names():
    specs = _by_name(extract_specs(ARTICLE, URL))
    for name in ("power", "torque", "price", "acceleration", "mileage", "top_speed"):
        assert name in specs, f"missing {name}"


def test_values_are_captured_with_units():
    specs = _by_name(extract_specs(ARTICLE, URL))
    assert specs["power"].value == "172 bhp"
    assert specs["torque"].value == "250 Nm"
    assert specs["price"].value == "Rs 12.99 lakh"
    assert specs["mileage"].value == "18 kmpl"
    assert specs["top_speed"].value == "180 km/h"


def test_source_sentence_is_verbatim_substring():
    # The linchpin: every source_sentence must appear literally in the article,
    # and the value must appear literally in its sentence.
    for spec in extract_specs(ARTICLE, URL):
        assert spec.source_sentence in ARTICLE
        assert spec.value in spec.source_sentence


def test_acceleration_only_from_a_sprint_sentence():
    # A stray "seconds" not tied to a 0-to-X sprint must NOT become a spec.
    text = "The infotainment system boots in 5 seconds."
    specs = _by_name(extract_specs(text, URL))
    assert "acceleration" not in specs


def test_boot_volume_is_not_read_as_engine_size():
    # Regression: "308-litre boot" must NOT yield an "8-litre" engine spec.
    text = "It has a 308-litre boot, larger than its rivals."
    specs = _by_name(extract_specs(text, URL))
    assert "engine_litre" not in specs


def test_no_specs_from_prose_without_figures():
    text = "The Example Car is a stylish and comfortable vehicle for the family."
    assert extract_specs(text, URL) == []
