"""Offline tests for mapping a retention curve onto script beats.

The whole point of the curve is answering WHERE viewers leave. Attribution must
land the loss on the beat that was on screen at that moment — an off-by-one here
would send the writer to rewrite a beat that was doing fine.
"""
import json

from carshorts.retention_watch import beat_drops

# hook 0-10s, spec 10-30s, cta 30-40s
MANIFEST = {
    "sections": [
        {"role": "hook", "duration": 10.0},
        {"role": "spec", "duration": 20.0},
        {"role": "cta", "duration": 10.0},
    ]
}


def _manifest(tmp_path):
    p = tmp_path / "v.manifest.json"
    p.write_text(json.dumps(MANIFEST), encoding="utf-8")
    return p


def test_attributes_loss_to_the_beat_on_screen(tmp_path):
    # audience holds through the hook, then falls hard during the spec beat
    curve = [[0.0, 1.0], [0.25, 1.0], [0.5, 0.6], [0.75, 0.55], [1.0, 0.5]]
    drops, worst = beat_drops(curve, _manifest(tmp_path))
    assert worst == "spec"
    assert drops["spec"] > drops.get("cta", 0)
    assert drops.get("hook", 0.0) == 0.0


def test_flat_curve_has_no_drops(tmp_path):
    curve = [[0.0, 1.0], [0.5, 1.0], [1.0, 1.0]]
    drops, worst = beat_drops(curve, _manifest(tmp_path))
    assert worst == ""
    assert all(v == 0.0 for v in drops.values())


def test_recoveries_never_count_as_loss(tmp_path):
    # a rewatch bump (audience ratio rising) must not register as negative loss
    curve = [[0.0, 1.0], [0.5, 0.4], [1.0, 0.9]]
    drops, _ = beat_drops(curve, _manifest(tmp_path))
    assert all(v >= 0.0 for v in drops.values())


def test_empty_curve_is_safe(tmp_path):
    drops, worst = beat_drops([], _manifest(tmp_path))
    assert drops == {} and worst == ""
