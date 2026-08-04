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


def _script(text, cited=None):
    return Script(subject="Test Car", segments=[
        ScriptSegment(role="hook", text=text, cited_spec_names=cited or []),
        ScriptSegment(role="cta", text="Sonet or Nexon? Comment 1 or 2.", cited_spec_names=[]),
    ])


def test_critique_returns_structured(monkeypatch):
    _use(monkeypatch, [{"verdict": "revise", "score": 6, "usp": "160 PS turbo",
                        "verdict_line": "worth it", "issues": []}])
    c = scriptbrain.critique(_script("Is it worth it?"), SHEET, "spotlight")
    assert c["verdict"] == "revise" and c["score"] == 6 and c["usp"] == "160 PS turbo"


def test_studio_pass_revises_until_bar(monkeypatch):
    original = _script("Is the Test Car worth it?")
    revised_json = {"subject": "Test Car", "segments": [
        {"role": "hook", "text": "It makes 160 PS — worth every rupee.", "cited_spec_names": ["power"]},
        {"role": "cta", "text": "Sonet or Nexon? Comment 1 or 2.", "cited_spec_names": []},
    ]}
    _use(monkeypatch, [
        {"verdict": "revise", "score": 5, "usp": "NONE",
         "issues": [{"beat": "hook", "fix": "lead with the 160 PS USP"}]},   # critique 1
        revised_json,                                                          # revise 1
        {"verdict": "ship", "score": 9, "usp": "160 PS turbo"},               # critique 2
    ])
    out, crit = scriptbrain.studio_pass(original, SHEET, "spotlight")
    assert crit["score"] == 9 and crit["verdict"] == "ship"
    assert "160 PS" in out.segments[0].text          # kept the clean revision


def test_studio_pass_rejects_unsourced_revision(monkeypatch):
    original = _script("Is the Test Car worth it?")
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
    assert out.segments[0].text == "Is the Test Car worth it?"


def test_rubric_for_falls_back():
    assert scriptbrain.rubric_for("vs") == scriptbrain.FORMAT_RUBRICS["vs"]
    assert scriptbrain.rubric_for("nonsense") == scriptbrain.FORMAT_RUBRICS["spotlight"]
