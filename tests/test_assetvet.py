"""Offline tests for the asset vet (vision call injected, no network).

The rules being locked in: a readable plate or a third-party watermark is a HARD
disqualifier (both are explicit CLAUDE.md non-negotiables), an older generation
is only advisory (an "old news" beat may want it deliberately), and a failure
is QUARANTINED not deleted — a vision model is advisory and the owner must be
able to overrule it.
"""
import json

from carshorts.quality.assetvet import (
    QUARANTINE,
    decide,
    parse_verdicts,
    quarantine_from_report,
    seed_cache_from_reports,
    vet_folder,
    vet_paths,
)


def _img(tmp_path, name):
    # a real (tiny) PNG so the glob and move paths are exercised honestly
    from PIL import Image
    p = tmp_path / name
    Image.new("RGB", (8, 8), (120, 120, 120)).save(p)
    return p


def test_plate_and_watermark_block():
    assert decide(["readable_plate"]) == (False, ["readable_plate"])
    assert decide(["watermark"]) == (False, ["watermark"])


def test_wrong_generation_is_advisory_only():
    ok, blocking = decide(["wrong_generation"])
    assert ok is True and blocking == []


def test_clean_image_passes():
    assert decide([]) == (True, [])


def test_parse_verdicts_tolerates_fences_and_prose():
    raw = 'here you go:\n```json\n[{"image":0,"defects":["readable_plate"],"note":"x"}]\n```'
    rows = parse_verdicts(raw)
    assert rows == [{"image": 0, "defects": ["readable_plate"], "note": "x"}]


def test_parse_verdicts_survives_garbage():
    assert parse_verdicts("not json") == []
    assert parse_verdicts("") == []


def test_quarantine_moves_only_failures(tmp_path):
    _img(tmp_path, "good.jpg")
    _img(tmp_path, "plated.jpg")

    def fake_vet(paths, subject, generation=""):
        rows = []
        for i, p in enumerate(paths):
            defects = ["readable_plate"] if "plated" in p.name else []
            rows.append({"image": i, "defects": defects, "note": ""})
        return json.dumps(rows)

    report = vet_folder(tmp_path, "Test Car", apply=True, vet_fn=fake_vet)

    assert report["checked"] == 2 and report["clean"] == 1 and report["quarantined"] == 1
    assert (tmp_path / "good.jpg").exists()
    assert not (tmp_path / "plated.jpg").exists()
    # quarantined, NOT deleted — recoverable
    assert (tmp_path / QUARANTINE / "plated.jpg").exists()


def test_report_only_mode_moves_nothing(tmp_path):
    _img(tmp_path, "plated.jpg")

    def fake_vet(paths, subject, generation=""):
        return json.dumps([{"image": 0, "defects": ["watermark"], "note": ""}])

    report = vet_folder(tmp_path, "Test Car", apply=False, vet_fn=fake_vet)
    assert report["quarantined"] == 0
    assert (tmp_path / "plated.jpg").exists()      # untouched


def test_vision_failure_leaves_assets_untouched(tmp_path):
    """If the model is unavailable the vet must degrade quietly — never
    quarantine on no evidence, and never block the render."""
    _img(tmp_path, "a.jpg")

    def boom(paths, subject, generation=""):
        raise RuntimeError("no API key")

    report = vet_folder(tmp_path, "Test Car", apply=True, vet_fn=boom)
    assert report["quarantined"] == 0 and report["errors"]
    assert report["unvetted"] == 1 and report["vetted"] == 0
    assert (tmp_path / "a.jpg").exists()


def test_one_failed_batch_does_not_sink_the_others(tmp_path):
    """The Creta failure mode: a 200-image folder ran as 15 batches; one failing
    batch aborted the whole run and discarded every result. Now a failed batch
    marks its images unvetted and the successful batches still land."""
    for i in range(6):
        _img(tmp_path, f"img{i}.jpg")

    calls = {"n": 0}

    def flaky(paths, subject, generation=""):
        calls["n"] += 1
        if calls["n"] == 2:                       # second batch trips a rate limit
            raise RuntimeError("429 rate limit")
        rows = []
        for i, p in enumerate(paths):
            defects = ["readable_plate"] if "img0" in p.name else []
            rows.append({"image": i, "defects": defects, "note": ""})
        return json.dumps(rows)

    report = vet_folder(tmp_path, "Test", apply=True, batch=2, vet_fn=flaky)

    assert report["checked"] == 6
    assert report["unvetted"] == 2                # the one failed batch
    assert report["vetted"] == 4
    assert report["quarantined"] == 1             # img0's real plate, still caught
    assert not (tmp_path / "img0.jpg").exists()   # quarantined
    # images in the failed batch stay put — never quarantined on no evidence
    assert (tmp_path / "img2.jpg").exists()
    assert (tmp_path / "img3.jpg").exists()


def test_vet_paths_is_cache_first_and_never_recalls(tmp_path):
    """Vet-on-use: a file vetted once is never vetted again — this is what keeps
    the 198-image Creta pool inside free quota across many renders."""
    a = _img(tmp_path, "a.jpg")
    cache = tmp_path / "cache.json"
    calls = {"n": 0}

    def once(paths, subject, generation=""):
        calls["n"] += 1
        return json.dumps([{"image": i, "defects": []} for i, _ in enumerate(paths)])

    vet_paths([a], "Test", cache_path=cache, vet_fn=once)
    vet_paths([a], "Test", cache_path=cache, vet_fn=once)   # second time: cached
    assert calls["n"] == 1
    got = vet_paths([a], "Test", cache_path=cache, vet_fn=once)
    assert got[str(a)]["cached"] is True and got[str(a)]["ok"] is True


def test_vet_paths_respects_the_per_render_call_cap(tmp_path):
    imgs = [_img(tmp_path, f"i{i}.jpg") for i in range(10)]
    cache = tmp_path / "cache.json"

    def counter(paths, subject, generation=""):
        return json.dumps([{"image": i, "defects": []} for i, _ in enumerate(paths)])

    got = vet_paths(imgs, "Test", max_calls=1, batch=2, cache_path=cache, vet_fn=counter)
    vetted = [v for v in got.values() if v["vetted"]]
    assert len(vetted) == 2                     # only one batch of 2 got vetted
    assert len(got) == 10                        # the rest returned unvetted, not dropped


def test_vet_paths_reports_blocking_defects(tmp_path):
    plated = _img(tmp_path, "plated.jpg")
    cache = tmp_path / "cache.json"

    def flag(paths, subject, generation=""):
        return json.dumps([{"image": 0, "defects": ["readable_plate"]}])

    got = vet_paths([plated], "Test", cache_path=cache, vet_fn=flag)
    assert got[str(plated)]["ok"] is False
    assert "readable_plate" in got[str(plated)]["blocking"]


def test_seed_cache_ingests_saved_reports(tmp_path):
    import json as _json
    root = tmp_path / "cars" / "creta" / "images"
    root.mkdir(parents=True)
    (root / "vet_report.json").write_text(_json.dumps({"results": [
        {"file": "clean.jpg", "ok": True, "defects": [], "vetted": True},
        {"file": "plated.jpg", "ok": False, "defects": ["readable_plate"],
         "blocking": ["readable_plate"], "vetted": True},
        {"file": "unknown.jpg", "ok": True, "defects": [], "vetted": False},
    ]}), encoding="utf-8")
    for n in ("clean.jpg", "plated.jpg", "unknown.jpg"):
        _img(root, n)
    cache = tmp_path / "cache.json"

    added = seed_cache_from_reports(tmp_path / "cars", cache_path=cache)
    assert added == 2      # the two VETTED rows; the unvetted one is not seeded

    # a subsequent vet_paths uses the seed and makes no calls
    calls = {"n": 0}

    def boom(paths, subject, generation=""):
        calls["n"] += 1
        raise AssertionError("should not be called — seeded")

    got = vet_paths([root / "plated.jpg"], "Creta", cache_path=cache, vet_fn=boom)
    assert calls["n"] == 0
    assert got[str(root / "plated.jpg")]["ok"] is False


def test_quarantine_from_report_moves_without_vetting(tmp_path):
    import json as _json
    _img(tmp_path, "good.jpg")
    _img(tmp_path, "bad.jpg")
    (tmp_path / "vet_report.json").write_text(_json.dumps({"results": [
        {"file": "good.jpg", "ok": True, "defects": [], "vetted": True},
        {"file": "bad.jpg", "ok": False, "defects": ["watermark"],
         "blocking": ["watermark"], "vetted": True},
    ]}), encoding="utf-8")

    moved = quarantine_from_report(tmp_path)
    assert moved == ["bad.jpg"]
    assert (tmp_path / "good.jpg").exists()
    assert (tmp_path / QUARANTINE / "bad.jpg").exists()
    assert not (tmp_path / "bad.jpg").exists()


def test_quota_error_stops_further_calls(tmp_path):
    """A 429/quota error is a daily cap, not transient — after it, the vet must
    stop calling (the first Creta run fired 32 doomed calls past quota death)."""
    for i in range(10):
        _img(tmp_path, f"img{i}.jpg")

    calls = {"n": 0}

    def quota_dead(paths, subject, generation=""):
        calls["n"] += 1
        raise RuntimeError("429 You exceeded your current quota")

    report = vet_folder(tmp_path, "Test", apply=True, batch=2, vet_fn=quota_dead)
    assert calls["n"] == 1                 # tried once, then gave up
    assert report["vetted"] == 0 and report["unvetted"] == 10
    assert report["quarantined"] == 0      # nothing touched on no evidence


def test_already_quarantined_files_are_not_rechecked(tmp_path):
    _img(tmp_path, "a.jpg")
    q = tmp_path / QUARANTINE
    q.mkdir()
    _img(q, "old_bad.jpg")

    def fake_vet(paths, subject, generation=""):
        return json.dumps([{"image": i, "defects": [], "note": ""}
                           for i, _ in enumerate(paths)])

    report = vet_folder(tmp_path, "Test Car", apply=False, vet_fn=fake_vet)
    assert report["checked"] == 1      # only a.jpg
