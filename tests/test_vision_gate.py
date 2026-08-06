"""The vision QA gate: a stock 'highway' clip once put plated Mercedes G-Wagons in
a hook and deterministic QA passed it. A vision pass over the render's frames turns
blocking defects (readable plate / wrong-vehicle / watermark) into a QA warning that
gates. Only the hard defects gate; clutter/dark stay advisory."""
from carshorts.rendering.produce import _vision_warning


def test_blocking_vision_defect_becomes_a_warning():
    vq = {"blocking": 2, "blocking_detail": [
        {"t": 1.0, "asset": "suv_driving_highway.mp4", "issues": ["readable_plate", "wrong_vehicle_type"]},
        {"t": 3.0, "asset": "suv_driving_highway.mp4", "issues": ["readable_plate"]},
    ]}
    w = _vision_warning(vq)
    assert w and w.startswith("VISION:")
    assert "readable_plate" in w and "wrong_vehicle_type" in w


def test_clean_render_has_no_warning():
    assert _vision_warning({"blocking": 0, "flagged": 1, "blocking_detail": []}) is None
    assert _vision_warning({}) is None
