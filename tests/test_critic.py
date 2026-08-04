"""Offline tests for the pre-Gate brain critic (agents/critic.py).

The critic runs an LLM over the finished render and writes a structured critique
onto the queue card. These tests use a fake LLM (no network) and redirect the
QUEUE/OUT dirs to a tmp path, so they verify the plumbing: it reads the latest
manifest, calls the model, and persists card['critique'] atomically — and that a
model failure degrades to an advisory 'revise', never a crash."""
import json

from carshorts.agents import critic
from carshorts.core import paths


class _FakeLLM:
    def __init__(self, payload):
        self._payload = payload

    def complete_json(self, _system, _user):
        return self._payload


def _seed(tmp_path, monkeypatch, manifest_name="tata-sierra_final"):
    queue = tmp_path / "queue"
    out = tmp_path / "out"
    queue.mkdir()
    out.mkdir()
    monkeypatch.setattr(paths, "QUEUE", queue)
    monkeypatch.setattr(paths, "OUT", out)
    (queue / "tata-sierra.json").write_text(json.dumps({
        "car": "Tata Sierra", "slug": "tata-sierra", "voice": "calm",
    }), encoding="utf-8")
    (out / f"{manifest_name}.manifest.json").write_text(json.dumps({
        "render": {"voice_engine": "chatterbox"},
        "quality_warnings": [],
        "sections": [
            {"role": "hook", "text": "Eleven and a half lakh, worth it?",
             "duration": 3.2, "cuts": [{"asset": "own/sierra_hero.mp4"}],
             "pops": [{"text": "₹11.49L"}]},
        ],
    }), encoding="utf-8")
    return queue


def test_critic_writes_critique_onto_card(tmp_path, monkeypatch):
    queue = _seed(tmp_path, monkeypatch)
    payload = {"verdict": "ship", "score": 8, "summary": "Tight hook, clips match.",
               "strengths": ["hero-number hook"], "issues": []}
    monkeypatch.setattr(critic, "make_llm", lambda *_a, **_k: _FakeLLM(payload))

    out = critic.run("tata-sierra")

    assert out["verdict"] == "ship"
    card = json.loads((queue / "tata-sierra.json").read_text(encoding="utf-8"))
    assert card["critique"]["verdict"] == "ship"
    assert card["critique"]["score"] == 8
    assert "reviewed_at" in card["critique"]


def test_critic_degrades_when_model_errors(tmp_path, monkeypatch):
    queue = _seed(tmp_path, monkeypatch)

    class _Boom:
        def complete_json(self, *_a, **_k):
            raise RuntimeError("model down")

    monkeypatch.setattr(critic, "make_llm", lambda *_a, **_k: _Boom())

    out = critic.run("tata-sierra")

    assert out["verdict"] == "revise"  # advisory fallback, never a crash
    card = json.loads((queue / "tata-sierra.json").read_text(encoding="utf-8"))
    assert card["critique"]["verdict"] == "revise"


def test_critic_noops_without_a_render(tmp_path, monkeypatch):
    queue = tmp_path / "queue"
    out = tmp_path / "out"
    queue.mkdir()
    out.mkdir()
    monkeypatch.setattr(paths, "QUEUE", queue)
    monkeypatch.setattr(paths, "OUT", out)
    (queue / "tata-sierra.json").write_text(json.dumps({"slug": "tata-sierra"}), encoding="utf-8")

    def _boom(*_a, **_k):
        raise AssertionError("must not call the LLM without a manifest")

    monkeypatch.setattr(critic, "make_llm", _boom)
    assert critic.run("tata-sierra") == {}


def test_overlay_coverage_is_deterministic():
    # the LLM once called three COVERED features 'naked mentions'; coverage is now
    # computed in Python so the critic can't hallucinate a missing overlay.
    text = "Creta fights back: ventilated seats, wireless charging, bigger touchscreen."
    assert critic._uncovered_features(text, ["VENTILATED SEATS", "WIRELESS CHARGING", "TOUCHSCREEN"]) == []
    # a genuinely naked feature IS caught
    assert critic._uncovered_features("It adds a panoramic sunroof and six airbags.",
                                      ["SUNROOF"]) == ["airbags"]


def test_summary_exposes_ground_truth_overlays():
    manifest = {"sections": [{
        "role": "value", "text": "ventilated seats and wireless charging",
        "cuts": [{"asset": "creta_interior_slow.mp4"}],
        "pops": [{"text": "VENTILATED SEATS"}, {"text": "WIRELESS CHARGING"}],
        "duration": 4.7,
    }]}
    beat = critic._summary({"car": "X"}, manifest)["beats"][0]
    assert beat["overlays_on_screen"] == ["VENTILATED SEATS", "WIRELESS CHARGING"]
    assert beat["uncovered_features"] == []      # both named features are covered
