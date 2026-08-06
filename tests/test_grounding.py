"""RAG fact-grounding: confidence must reflect WHERE a fact came from and whether
sources agree — so a lone Wikipedia fact (the '1.5L Fronx' class) scores low and
gets flagged [CLAIMED], while two trusted sources agreeing score high."""
from carshorts.sourcing.webresearch import _norm_value, _tier, merge_and_score


def test_source_tiers():
    assert _tier("https://www.cardekho.com/mg/hector") == 1        # spec authority
    assert _tier("https://www.mgmotor.co.in/x") == 1               # official maker
    assert _tier("https://en.wikipedia.org/wiki/MG_Hector") == 2   # wikipedia
    assert _tier("https://randomblog.example/car") == 3            # unknown


def test_value_normalization():
    assert _norm_value("160 PS") == _norm_value("160ps") == "160ps"


def test_corroborated_two_trusted_sources_high_confidence():
    per = [("power", "160 PS", "https://cardekho.com/x", "s1", 1),
           ("power", "160 ps", "https://autocarindia.com/y", "s2", 1)]
    specs = merge_and_score(per)
    assert len(specs) == 1 and specs[0].confidence == 0.9


def test_single_authoritative_source_medium_high():
    specs = merge_and_score([("torque", "255 Nm", "https://cardekho.com/x", "s", 1)])
    assert specs[0].confidence == 0.8      # trusted but uncorroborated


def test_lone_wikipedia_fact_is_flagged_claimed():
    specs = merge_and_score([("engine", "1.5-litre", "https://en.wikipedia.org/wiki/x", "s", 2)])
    assert specs[0].confidence == 0.5      # < 0.7 -> render_spec_sheet marks it [CLAIMED]


def test_conflicting_sources_take_authoritative_but_flag():
    per = [("power", "160 PS", "https://cardekho.com/x", "s", 1),
           ("power", "150 PS", "https://en.wikipedia.org/wiki/x", "s", 2)]
    sp = merge_and_score(per)[0]
    assert sp.value == "160 PS"            # surface the authoritative value
    assert sp.confidence == 0.5            # but flag it — sources disagree
