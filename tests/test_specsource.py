"""Offline tests for the deterministic spec extractor.

No network: we feed known article-style prose and assert the extractor lifts
values bound to their VERBATIM source sentence. This is the honesty gate the
whole harness depends on — if extraction ever paraphrases, the hallucination
number it produces would be measuring against a fabricated answer key.
"""
from carshorts.adapters.specsource import extract_specs, scope_to_current_generation

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


def test_model_code_is_not_read_as_price():
    # Regression: "RS413" (a Swift engine/model code) must NOT become a price.
    text = "The Swift is offered in RS413 and RS415 trims for the market."
    specs = _by_name(extract_specs(text, URL))
    assert "price" not in specs


def test_section_header_not_used_as_source():
    # A "=== ... ===" header is not a real sentence; nothing should extract from it.
    text = "=== RS413/413D/415 ===\nSome later prose with 100 bhp of power."
    specs = _by_name(extract_specs(text, URL))
    assert all("==" not in s.source_sentence for s in specs.values())


def test_real_price_still_extracted():
    text = "Prices start at Rs 7.37 lakh ex-showroom."
    specs = _by_name(extract_specs(text, URL))
    assert "price" in specs and "7.37" in specs["price"].value


_MULTI_GEN = (
    "The Example Swift is a hatchback.\n"
    "== First generation (2004–2010) ==\n"
    "=== Engine ===\n"
    "The first-gen used a 1.3-litre engine making 65 kW and 120 N⋅m.\n"
    "== Fourth generation (2024–present) ==\n"
    "=== Engine ===\n"
    "The current model uses a 1.2-litre engine producing 82 PS and 111 N⋅m of torque.\n"
)


def test_scope_picks_current_generation_including_subsections():
    scoped = scope_to_current_generation(_MULTI_GEN)
    assert "1.2-litre" in scoped and "82 PS" in scoped   # current gen kept
    assert "1.3-litre" not in scoped and "65 kW" not in scoped   # old gen dropped


def test_scoped_extraction_uses_current_specs_only():
    specs = _by_name(extract_specs(scope_to_current_generation(_MULTI_GEN), URL))
    assert specs["engine_litre"].value == "1.2-litre"
    assert specs["power"].value == "82 PS"


def test_scope_falls_back_when_no_generation_sections():
    # A single-generation article (no gen headers) is returned unchanged.
    plain = "The car makes 100 kW. It is efficient."
    assert scope_to_current_generation(plain) == plain


def test_no_specs_from_prose_without_figures():
    text = "The Example Car is a stylish and comfortable vehicle for the family."
    assert extract_specs(text, URL) == []
