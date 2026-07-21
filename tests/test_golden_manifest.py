"""Golden-manifest integration test — the whole planning pipeline, offline.

Runs produce(plan_only=True) with the mock TTS and a fixture asset tree, then
asserts every hard-won invariant on the manifest:
  - cuts monotonic, none shorter than ~1s
  - no asset repeated beyond the mathematically unavoidable budget
  - video opens AND closes on the subject car
  - keyword spans and callout windows sit inside their sections
If a refactor breaks phrase-sync, assignment, or overlay timing, this fails
in seconds — no video render, no network, no keys.
"""
import json
import os
from pathlib import Path

import pytest

from carshorts.models import Script, SpecSheet


CAR_FAMILIES = {"roxx", "red", "thar", "pool", "testcar"}


@pytest.fixture()
def fixture_tree(tmp_path, monkeypatch):
    """A minimal project tree: spec sheet, script, 6 'car' images, 2 stock mp4s."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "specs").mkdir()
    sheet = {
        "subject": "Test Car",
        "specs": [
            {"name": "power", "value": "100 PS",
             "source_url": "https://example.com/a",
             "source_sentence": "It makes 100 PS."},
            {"name": "torque", "value": "200 Nm",
             "source_url": "https://example.com/a",
             "source_sentence": "It makes 200 Nm."},
        ],
    }
    (tmp_path / "specs" / "test-car.json").write_text(json.dumps(sheet))

    script = {
        "subject": "Test Car",
        "segments": [
            {"role": "hook", "text": "Is the Test Car actually the smart buy this year, or a trap?",
             "cited_spec_names": []},
            {"role": "spec", "text": "It makes 100 PS of power, and 200 Nm of torque, which is plenty.",
             "cited_spec_names": ["power", "torque"]},
            {"role": "peak", "text": "Buying rivals instead? Bold move. Genuinely bold.",
             "cited_spec_names": []},
            {"role": "cta", "text": "Would you take one home? Say it in the comments, and follow.",
             "cited_spec_names": []},
        ],
    }
    (tmp_path / "script.json").write_text(json.dumps(script))

    from PIL import Image
    img_dir = tmp_path / "assets" / "cars" / "test-car" / "images"
    img_dir.mkdir(parents=True)
    for i in range(6):
        Image.new("RGB", (720, 1280), (30 + i * 20, 60, 90)).save(img_dir / f"testcar_view{i}.jpg")

    (tmp_path / "assets" / "stock").mkdir(parents=True)
    (tmp_path / "assets" / "music").mkdir(parents=True)
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "out").mkdir(exist_ok=True)
    return tmp_path


def test_plan_manifest_invariants(fixture_tree, monkeypatch):
    # force FULLY offline: no LLM matching, no stock fetch, no vision
    for key in ("GROQ_API_KEY", "PEXELS_API_KEY", "GEMINI_API_KEY", "ELEVENLABS_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("CARSHORTS_LLM", "ollama")   # never reached without a matcher key
    from carshorts.produce import produce

    manifest_path = produce(
        spec_path="specs/test-car.json",
        out_path="out/test_car.mp4",
        script_file="script.json",
        skip_factcheck=True,
        voice_engine="mock",
        provider=None,
        plan_only=True,
        music="none",
        stock=False,
    )
    manifest = json.loads(Path(manifest_path).read_text())
    sections = manifest["sections"]
    assert len(sections) == 4

    all_assets = []
    for sec in sections:
        times = [c["t"] for c in sec["cuts"]]
        assert times == sorted(times), f"cuts not monotonic in section {sec['index']}"
        spans = [b - a for a, b in zip(times, times[1:])]
        assert all(sp >= 1.0 for sp in spans), f"cut shorter than 1s in section {sec['index']}"
        all_assets += [c["asset"] for c in sec["cuts"]]

        kw = sec["keyword"]
        if kw["text"]:
            assert 0 <= kw["start"] < sec["duration"]
        for co in sec["callouts"]:
            assert co["start"] < sec["duration"] - 0.3
            assert co["end"] <= sec["duration"] + 0.01

    repeats = len(all_assets) - len(set(all_assets))
    allowed = max(0, len(all_assets) - manifest["pool_size"])
    assert repeats <= allowed, f"{repeats} repeats vs {allowed} allowed"

    def family(asset):
        return Path(asset).stem.split("_")[0].lower()
    assert family(sections[0]["cuts"][0]["asset"]) in CAR_FAMILIES
    assert family(sections[-1]["cuts"][-1]["asset"]) in CAR_FAMILIES


def test_plan_manifest_no_kwcaps(fixture_tree, monkeypatch):
    """--no-kwcaps (owner ordered text overlays off) must render a manifest
    with zero on-screen text — and must not crash on the None keyword span."""
    for key in ("GROQ_API_KEY", "PEXELS_API_KEY", "GEMINI_API_KEY", "ELEVENLABS_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("CARSHORTS_LLM", "ollama")
    from carshorts.produce import produce

    manifest_path = produce(
        spec_path="specs/test-car.json",
        out_path="out/test_car_notext.mp4",
        script_file="script.json",
        skip_factcheck=True,
        voice_engine="mock",
        provider=None,
        plan_only=True,
        music="none",
        stock=False,
        kwcaps=False,
    )
    for sec in json.loads(Path(manifest_path).read_text())["sections"]:
        assert sec["keyword"]["text"] == ""
        assert sec["callouts"] == []


def test_phrase_times_monotonic(fixture_tree):
    from carshorts.produce import _phrases_with_times
    from carshorts.adapters.tts import SilentTTSProvider

    text = "First the hook lands here, then a second idea follows, and a third one closes."
    SilentTTSProvider().synthesize(text, "voice.wav", marks_path="marks.json")
    phrases = _phrases_with_times(text, "marks.json")
    assert len(phrases) >= 2
    times = [t for t, _ in phrases]
    assert times == sorted(times)
    assert times[0] == 0.0
