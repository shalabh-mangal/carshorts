"""RAG fact-grounding: confidence must reflect WHERE a fact came from and whether
sources agree. Wikipedia is REMOVED as a fact source (the '1.5L Fronx' class of
wrong India spec), so it is a BLOCKED tier and never grounds a fact; a lone weak
source scores low ([CLAIMED]) while two trusted sources agreeing score high."""
from carshorts.sourcing.webresearch import _norm_value, _tier, merge_and_score


def test_source_tiers():
    assert _tier("https://www.cardekho.com/mg/hector") == 1        # spec authority
    assert _tier("https://www.mgmotor.co.in/x") == 1               # official maker
    assert _tier("https://www.nexaexperience.com/fronx") == 1      # official Nexa
    assert _tier("https://randomblog.example/car") == 3            # unknown


def test_wikipedia_is_blocked_not_trusted():
    # Wikipedia (and mirrors) must never rank as a usable source; grounding uses
    # tier-1 only, so tier 9 keeps it out entirely.
    assert _tier("https://en.wikipedia.org/wiki/MG_Hector") == 9
    assert _tier("https://www.wikiwand.com/en/MG_Hector") == 9
    assert _tier("https://en.wikipedia.org/wiki/MG_Hector") != 1


def test_crawl_delegates_to_grounded_research_never_conf_1():
    # `crawl` used to write conf=1.0 ungrounded Wikipedia specs (the "1.5L Fronx"
    # trap). It now delegates to the grounded research path, whose scores top out
    # at 0.9 — a spec can never re-enter a sheet at a falsely-confident 1.0.
    from carshorts.sourcing import crawl, webresearch
    assert crawl.research is webresearch.research
    scored = merge_and_score([
        ("power", "160 PS", "https://cardekho.com/x", "s1", 1),
        ("power", "160 ps", "https://autocarindia.com/y", "s2", 1),
        ("torque", "255 Nm", "https://cardekho.com/x", "s", 1),
    ])
    assert scored and all(s.confidence <= 0.9 for s in scored)


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


def test_lone_weak_source_is_flagged_claimed():
    specs = merge_and_score([("engine", "1.5-litre", "https://randomblog.example/x", "s", 3)])
    assert specs[0].confidence == 0.5      # < 0.7 -> render_spec_sheet marks it [CLAIMED]


def test_conflicting_sources_take_authoritative_but_flag():
    per = [("power", "160 PS", "https://cardekho.com/x", "s", 1),
           ("power", "150 PS", "https://randomblog.example/x", "s", 3)]
    sp = merge_and_score(per)[0]
    assert sp.value == "160 PS"            # surface the authoritative value
    assert sp.confidence == 0.5            # but flag it — sources disagree
