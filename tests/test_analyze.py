"""The analytics learnings-merge: data-derived observations roll on a window, but
hand-curated [process]/[mechanic] craft rules are PINNED and never rolled off.
Regression guard — `[-12:]` once silently dropped the step4/step5/vision-fp
process learnings when the list grew past 12."""
from carshorts.intel.analyze import _merge_learnings


def test_pinned_learnings_survive_the_window():
    pinned = ["[high][process][step4] run footage cockpit first",
              "[high][mechanic][vision-fp] tiered blocking"]
    rolling = [f"[low] observation {i}" for i in range(20)]
    out = _merge_learnings(pinned + rolling, [], keep=12)
    # every pinned rule is retained, regardless of the rolling cap
    for p in pinned:
        assert p in out
    # rolling capped to the last 12
    rolling_out = [l for l in out if l not in pinned]
    assert len(rolling_out) == 12
    assert rolling_out[-1] == "[low] observation 19"


def test_new_learnings_appended_and_deduped():
    existing = ["[low] a", "[medium] b"]
    out = _merge_learnings(existing, ["[medium] b", "[high] c"])  # b is a dup
    assert out.count("[medium] b") == 1
    assert "[high] c" in out


def test_pinned_kept_in_full_even_beyond_keep():
    pinned = [f"[high][process] rule {i}" for i in range(15)]   # 15 pinned > keep
    out = _merge_learnings(pinned, [], keep=12)
    assert len([l for l in out if "[process]" in l]) == 15      # none rolled off


def test_pinned_ordered_before_rolling():
    merged = _merge_learnings(["[low] obs", "[high][process] rule"], [])
    assert merged.index("[high][process] rule") < merged.index("[low] obs")
