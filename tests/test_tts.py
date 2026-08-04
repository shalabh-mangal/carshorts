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


def test_resolves_lakh_and_litres():
    # decimal L = price in lakh; ₹-context L = lakh; integer L = capacity in litres
    assert normalize_for_speech("Sierra 11.49L, Creta 10.91L") == \
        "Sierra 11.49 lakh, Creta 10.91 lakh"
    assert normalize_for_speech("₹11.49L") == "11.49 lakh"
    assert normalize_for_speech("a 622L boot") == "a 622 litres boot"
    assert normalize_for_speech("45L tank") == "45 litres tank"


def test_expands_shorthand_for_voice():
    assert normalize_for_speech("costs 58k more") == "costs 58 thousand more"
    assert normalize_for_speech("Sierra vs Creta") == "Sierra versus Creta"
    assert normalize_for_speech("13-speaker JBL") == "13 speaker JBL"
    assert normalize_for_speech("160+ PS") == "160 plus P-S"
    assert normalize_for_speech("brakes & ADAS") == "brakes and driver assist"


def test_leaves_normal_words_alone():
    assert normalize_for_speech("The Swift is efficient at 25.75 kmpl") == \
        "The Swift is efficient at 25.75 kmpl"
    # a word ending in 'l' must not be mistaken for a litres/lakh unit
    assert normalize_for_speech("all metal panels") == "all metal panels"
