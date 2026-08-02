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
from pathlib import Path

import pytest

CAR_FAMILIES = {"roxx", "red", "thar", "pool", "testcar"}


@pytest.fixture()
def fixture_tree(tmp_path, monkeypatch):
    """A minimal project tree: spec sheet, script, 6 'car' images, 2 stock mp4s."""
    monkeypatch.chdir(tmp_path)
    # produce & friends read every dir from core.paths (ROOT-anchored). Re-root
    # that layout onto this fixture tree so the render sees the fixture's
    # assets/specs/out, not the real repo's.
    import carshorts.core.paths as _paths
    _orig_root = _paths.ROOT               # save before patching ROOT below
    for _name in dir(_paths):
        _val = getattr(_paths, _name)
        if _name.isupper() and isinstance(_val, Path):
            try:
                _rel = _val.relative_to(_orig_root)
            except ValueError:
                continue
            monkeypatch.setattr(_paths, _name, tmp_path / _rel)
    monkeypatch.setattr(_paths, "ROOT", tmp_path)
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
             "cited_spec_names": [],
             "pops": ["Bold move",
                      {"anchor": "Genuinely bold", "show": "INSPIRED."}]},
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


def test_pops_generated_for_spec_figures(fixture_tree, monkeypatch):
    """The spec beat carries '100 PS' and '200 Nm'; the peak curates 'Bold
    move' — with the mock voice timeline, pops must actually appear."""
    for key in ("GROQ_API_KEY", "PEXELS_API_KEY", "GEMINI_API_KEY", "ELEVENLABS_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("CARSHORTS_LLM", "ollama")
    from carshorts.rendering.produce import produce

    manifest_path = produce(
        spec_path="specs/test-car.json",
        out_path="out/test_car_pops.mp4",
        script_file="script.json",
        skip_factcheck=True,
        voice_engine="mock",
        provider=None,
        plan_only=True,
        music="none",
        stock=False,
    )
    sections = json.loads(Path(manifest_path).read_text())["sections"]
    spec_pops = [p["text"] for p in sections[1]["pops"]]
    assert "100 PS" in spec_pops, spec_pops
    peak_pops = {p["text"]: p for p in sections[2]["pops"]}
    assert "Bold move" in peak_pops, peak_pops
    assert peak_pops["Bold move"]["kind"] == "word"
    # reaction pop: non-transcript text, fires AFTER its anchor is spoken
    assert "INSPIRED." in peak_pops, peak_pops
    reaction = peak_pops["INSPIRED."]
    assert reaction["kind"] == "reaction"
    assert reaction["start"] > peak_pops["Bold move"]["start"]
    spec_kinds = {p["text"]: p["kind"] for p in sections[1]["pops"]}
    assert spec_kinds.get("100 PS") == "number"


def test_plan_manifest_invariants(fixture_tree, monkeypatch):
    # force FULLY offline: no LLM matching, no stock fetch, no vision
    for key in ("GROQ_API_KEY", "PEXELS_API_KEY", "GEMINI_API_KEY", "ELEVENLABS_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("CARSHORTS_LLM", "ollama")   # never reached without a matcher key
    from carshorts.rendering.produce import produce

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

        # word-synced pops: <=2, ordered, non-overlapping, inside the section,
        # and every pop's words must exist in the spoken line (word-exact source)
        pops = sec["pops"]
        assert len(pops) <= 6
        section_words = {w.strip('.,?!—').lower() for w in sec["text"].split()}
        prev_end = -1.0
        for pop in pops:
            own_slot = pop["kind"] in ("reaction", "card", "lss")
            if not own_slot:
                assert pop["start"] >= prev_end + 0.04, f"pops crowd sec {sec['index']}"
            assert 0 <= pop["start"] < sec["duration"] - 0.3
            if pop["kind"] == "reaction":
                # written editorial text, straddles the cut — words are NOT
                # transcript, so no word-source check
                prev_end = pop["start"] + pop["dur"]
                continue
            assert pop["start"] + pop["dur"] <= sec["duration"] + 0.6
            # lss + card pops carry synthetic tags ('LSS', figures) rather
            # than transcript words — skip the word-source check for them
            if pop["kind"] not in ("lss", "card"):
                for w in pop["text"].split():
                    assert w.strip('.,?!—').lower() in section_words
            prev_end = pop["start"] + pop["dur"]

    repeats = len(all_assets) - len(set(all_assets))
    allowed = max(0, len(all_assets) - manifest["pool_size"])
    assert repeats <= allowed, f"{repeats} repeats vs {allowed} allowed"

    def family(asset):
        return Path(asset).stem.split("_")[0].lower()
    assert family(sections[0]["cuts"][0]["asset"]) in CAR_FAMILIES
    assert family(sections[-1]["cuts"][-1]["asset"]) in CAR_FAMILIES


def test_lss_graphic_generated_from_cta(fixture_tree, monkeypatch):
    """CTA narration containing 'like, share, subscribe' (any punctuation)
    auto-generates a pop with kind='lss'. The renderer draws the three-icon
    graphic strip in place of transcript text — no text pop needed."""
    for key in ("GROQ_API_KEY", "PEXELS_API_KEY", "GEMINI_API_KEY", "ELEVENLABS_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("CARSHORTS_LLM", "ollama")
    from carshorts.rendering.produce import produce

    script = {
        "subject": "Test Car",
        "segments": [
            {"role": "hook", "text": "Is the Test Car actually the smart buy this year, or a trap?",
             "cited_spec_names": [], "pops": []},
            {"role": "cta", "text": "Which car should get this treatment next? Comment below — and like, share, subscribe.",
             "cited_spec_names": [], "pops": []},
        ],
    }
    Path("script_lss.json").write_text(json.dumps(script))
    manifest_path = produce(
        spec_path="specs/test-car.json",
        out_path="out/test_car_lss.mp4",
        script_file="script_lss.json",
        skip_factcheck=True,
        voice_engine="mock",
        provider=None,
        plan_only=True,
        music="none",
        stock=False,
    )
    sections = json.loads(Path(manifest_path).read_text())["sections"]
    cta_pops = sections[-1]["pops"]
    kinds = [p["kind"] for p in cta_pops]
    assert "lss" in kinds, f"lss pop missing from CTA — got {cta_pops}"
    lss = [p for p in cta_pops if p["kind"] == "lss"]
    # the strip is revealed word-by-word: LIKE -> SHARE -> SUBSCRIBE pops,
    # each timed to its spoken word, later starts strictly after earlier ones
    assert [p["text"] for p in lss] == ["LIKE", "SHARE", "SUBSCRIBE"], lss
    starts = [p["start"] for p in lss]
    assert starts == sorted(starts) and len(set(starts)) == 3
    assert lss[0]["start"] > 0.0
    assert all(p["dur"] >= 0.3 for p in lss)


def test_plan_manifest_no_kwcaps(fixture_tree, monkeypatch):
    """--no-kwcaps (owner ordered text overlays off) must render a manifest
    with zero on-screen text — and must not crash on the None keyword span."""
    for key in ("GROQ_API_KEY", "PEXELS_API_KEY", "GEMINI_API_KEY", "ELEVENLABS_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("CARSHORTS_LLM", "ollama")
    from carshorts.rendering.produce import produce

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
        assert sec["pops"] == []


def test_dropped_overlay_is_flagged(fixture_tree, monkeypatch):
    """A scripted overlay whose anchor is never spoken must surface as a
    'DROPPED' quality warning (so QA turns red) — never vanish silently. This
    is the guard for the missed SUNROOF / SUBSCRIBE class of defect."""
    for key in ("GROQ_API_KEY", "PEXELS_API_KEY", "GEMINI_API_KEY", "ELEVENLABS_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("CARSHORTS_LLM", "ollama")
    from carshorts.rendering.produce import produce

    script = {
        "subject": "Test Car",
        "segments": [
            {"role": "hook", "text": "Is the Test Car the smart buy this year, or a trap?",
             "cited_spec_names": [], "pops": []},
            {"role": "spec", "text": "It makes 100 PS of power, and 200 Nm of torque, which is plenty.",
             "cited_spec_names": ["power", "torque"],
             "pops": [{"anchor": "sunroof", "show": "SUNROOF"}]},   # 'sunroof' never spoken
            {"role": "cta", "text": "Would you take one home? Say it in the comments, and follow.",
             "cited_spec_names": [], "pops": []},
        ],
    }
    Path("script_drop.json").write_text(json.dumps(script))
    manifest_path = produce(
        spec_path="specs/test-car.json", out_path="out/test_drop.mp4",
        script_file="script_drop.json", skip_factcheck=True, voice_engine="mock",
        provider=None, plan_only=True, music="none", stock=False,
    )
    warns = json.loads(Path(manifest_path).read_text()).get("quality_warnings", [])
    assert any(w.startswith("DROPPED") and "SUNROOF" in w for w in warns), warns


def test_stills_never_flagged_as_loops():
    """Loop detection must ignore stills (a still legitimately fills any cut) —
    only real video clips shorter than their cut count as looped footage. This
    is why the still-based golden fixtures don't trip the loop gate."""
    from carshorts.rendering.produce import _video_duration
    assert _video_duration("assets/foo.jpg") is None
    assert _video_duration("assets/bar.png") is None


def test_phrase_times_monotonic(fixture_tree):
    from carshorts.adapters.tts import SilentTTSProvider
    from carshorts.rendering.produce import _phrases_with_times

    text = "First the hook lands here, then a second idea follows, and a third one closes."
    SilentTTSProvider().synthesize(text, "voice.wav", marks_path="marks.json")
    phrases = _phrases_with_times(text, "marks.json")
    assert len(phrases) >= 2
    times = [t for t, _ in phrases]
    assert times == sorted(times)
    assert times[0] == 0.0
