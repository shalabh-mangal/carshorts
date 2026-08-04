"""Offline tests for the Script Brain (format-aware critique + revise loop).

Uses a fake LLM (no network): a shared response queue drives the
critique -> revise -> critique sequence. Verifies the loop revises up to the bar,
and — critically — never keeps a revision that introduces an unsourced fact."""
from carshorts.core.models import Script, ScriptSegment, Spec, SpecSheet
from carshorts.writing import scriptbrain

SHEET = SpecSheet(subject="Test Car", specs=[
    Spec(name="power", value="160 PS", source_url="https://example.com/spec",
         source_sentence="The Test Car makes 160 PS.", confidence=1.0),
])


class _FakeLLM:
    """Pops a shared queue so successive critique/revise calls get scripted JSON."""

    def __init__(self, responses):
        self._r = list(responses)

    def complete_json(self, system, user):
        return self._r.pop(0) if self._r else {}


def _use(monkeypatch, responses):
    fake = _FakeLLM(responses)
    monkeypatch.setattr(scriptbrain, "make_llm", lambda *_a, **_k: fake)


def _full(hook="Is the Test Car really worth your money this year, or a total trap?"):
    """A structurally COMPLETE 5-beat, >=55-word script with a like/share/subscribe
    CTA — so the deterministic completeness guard passes and we test the LLM score."""
    return Script(subject="Test Car", segments=[
        ScriptSegment(role="hook", text=hook, cited_spec_names=[]),
        ScriptSegment(role="spec", text="It makes a hundred and sixty PS of turbo power, plenty for the price.",
                      cited_spec_names=["power"]),
        ScriptSegment(role="value", text="It comes loaded with features that punch well above its class, honestly.",
                      cited_spec_names=[]),
        ScriptSegment(role="peak", text="For this kind of money it is a genuine steal, no contest at all here.",
                      cited_spec_names=[]),
        ScriptSegment(role="cta", text="So, Sonet or Nexon? Comment one or two below. Like, share, subscribe.",
                      cited_spec_names=[]),
    ])


def _full_json(hook="It makes a hundred and sixty PS turbo, worth every rupee at the price."):
    return {"subject": "Test Car", "segments": [
        {"role": "hook", "text": hook, "cited_spec_names": ["power"]},
        {"role": "spec", "text": "That turbo power leaves rivals wheezing behind on any open road.", "cited_spec_names": []},
        {"role": "value", "text": "And it stays properly loaded with the features buyers actually want daily.", "cited_spec_names": []},
        {"role": "peak", "text": "For the money, honestly, nothing else comes remotely close to it.", "cited_spec_names": []},
        {"role": "cta", "text": "So, Sonet or Nexon? Comment one or two. Like, share, subscribe.", "cited_spec_names": []},
    ]}


def test_critique_returns_structured(monkeypatch):
    _use(monkeypatch, [{"verdict": "revise", "score": 6, "usp": "160 PS turbo",
                        "verdict_line": "worth it", "issues": []}])
    c = scriptbrain.critique(_full(), SHEET, "spotlight")
    assert c["verdict"] == "revise" and c["score"] == 6 and c["usp"] == "160 PS turbo"


def test_incomplete_script_cannot_ship(monkeypatch):
    # even if the LLM says ship 9, a 2-beat/no-subscribe script is forced to revise
    thin = Script(subject="Test Car", segments=[
        ScriptSegment(role="hook", text="Big number, big deal.", cited_spec_names=[]),
        ScriptSegment(role="cta", text="Comment below.", cited_spec_names=[]),
    ])
    _use(monkeypatch, [{"verdict": "ship", "score": 9, "usp": "power"}])
    c = scriptbrain.critique(thin, SHEET, "spotlight")
    assert c["verdict"] == "revise" and c["score"] <= 4
    beats = {i["beat"] for i in c["issues"]}
    assert "structure" in beats and "cta" in beats      # missing beats + no subscribe


def test_studio_pass_revises_until_bar(monkeypatch):
    original = _full()
    _use(monkeypatch, [
        {"verdict": "revise", "score": 5, "usp": "NONE",
         "issues": [{"beat": "hook", "fix": "lead with the 160 PS USP"}]},   # critique 1
        _full_json(),                                                         # revise 1 (complete)
        {"verdict": "ship", "score": 9, "usp": "160 PS turbo"},              # critique 2
    ])
    out, crit = scriptbrain.studio_pass(original, SHEET, "spotlight")
    assert crit["score"] == 9 and crit["verdict"] == "ship"
    assert "hundred and sixty" in out.segments[0].text   # kept the clean revision


def test_studio_pass_rejects_unsourced_revision(monkeypatch):
    original = _full()
    bad_json = {"subject": "Test Car", "segments": [
        {"role": "hook", "text": "Zero to hundred in 8 seconds flat.", "cited_spec_names": []},
        {"role": "cta", "text": "Comment below.", "cited_spec_names": []},
    ]}
    _use(monkeypatch, [
        {"verdict": "revise", "score": 5, "issues": [{"beat": "hook", "fix": "add a number"}]},
        bad_json,   # introduces an unsourced "8 seconds" -> must be rejected
    ])
    out, _crit = scriptbrain.studio_pass(original, SHEET, "spotlight")
    # the unsourced revision is dropped; the original (clean) script is kept
    assert out.segments[0].text == original.segments[0].text


def test_rubric_for_falls_back():
    assert scriptbrain.rubric_for("vs") == scriptbrain.FORMAT_RUBRICS["vs"]
    assert scriptbrain.rubric_for("nonsense") == scriptbrain.FORMAT_RUBRICS["spotlight"]


def test_mine_angles_validates_format(monkeypatch):
    _use(monkeypatch, [{"angles": [
        {"format": "vs", "hook": "h", "usp": "u", "verdict": "v", "why": "w"},
        {"format": "bogus", "hook": "h2", "usp": "u2"},        # invalid -> spotlight
    ]}])
    angles = scriptbrain.mine_angles(SHEET, "context", n=3)
    assert len(angles) == 2
    assert angles[0]["format"] == "vs"
    assert angles[1]["format"] == "spotlight"


def test_mine_angles_empty_on_error(monkeypatch):
    class _Boom:
        def complete_json(self, *_a, **_k):
            raise RuntimeError("provider down")
    monkeypatch.setattr(scriptbrain, "make_llm", lambda *_a, **_k: _Boom())
    assert scriptbrain.mine_angles(SHEET) == []
