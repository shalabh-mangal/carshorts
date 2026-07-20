"""Offline tests for speech normalization — scripts stay clean, TTS sounds right."""
from carshorts.adapters.tts import normalize_for_speech


def test_drops_rupee_symbol():
    assert normalize_for_speech("₹5.79 lakh") == "5.79 lakh"
    assert normalize_for_speech("Rs 5.79 lakh") == "5.79 lakh"


def test_spells_out_acronym_units():
    assert normalize_for_speech("82 PS") == "82 P-S"
    assert normalize_for_speech("111.7 N⋅m") == "111.7 N-m"
    assert normalize_for_speech("111.7 Nm") == "111.7 N-m"
    assert normalize_for_speech("80 bhp") == "80 B-H-P"
    assert normalize_for_speech("60 kW") == "60 k-W"


def test_leaves_normal_words_alone():
    assert normalize_for_speech("The Swift is efficient at 25.75 kmpl") == \
        "The Swift is efficient at 25.75 kmpl"
