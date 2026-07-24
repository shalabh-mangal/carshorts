"""Offline tests for first-frame metrics (synthetic images, no network).

These metrics are the objective half of first-frame work — they must behave
predictably on images whose properties we know by construction, otherwise the
rival benchmark built on top of them means nothing.
"""
from carshorts.firstframe import KEYS, _aggregate, compare, frame_stats


def _solid(tmp_path, name, rgb, size=(64, 64)):
    from PIL import Image
    p = tmp_path / name
    Image.new("RGB", size, rgb).save(p)
    return p


def _checker(tmp_path, name, size=64, cell=8):
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (size, size), (0, 0, 0))
    d = ImageDraw.Draw(img)
    for y in range(0, size, cell):
        for x in range(0, size, cell):
            if (x // cell + y // cell) % 2 == 0:
                d.rectangle([x, y, x + cell - 1, y + cell - 1], fill=(255, 255, 255))
    p = tmp_path / name
    img.save(p)
    return p


def test_flat_grey_has_no_contrast_or_colour(tmp_path):
    s = frame_stats(_solid(tmp_path, "grey.png", (128, 128, 128)))
    assert s["contrast"] == 0.0
    assert s["saturation"] == 0.0
    assert s["colorfulness"] < 1.0
    assert s["brightness"] == 128.0


def test_checkerboard_has_high_contrast_and_edges(tmp_path):
    flat = frame_stats(_solid(tmp_path, "flat.png", (128, 128, 128)))
    busy = frame_stats(_checker(tmp_path, "busy.png"))
    assert busy["contrast"] > flat["contrast"]
    assert busy["edge_density"] > flat["edge_density"]


def test_saturated_colour_beats_grey_on_colourfulness(tmp_path):
    grey = frame_stats(_solid(tmp_path, "g.png", (128, 128, 128)))
    red = frame_stats(_solid(tmp_path, "r.png", (255, 0, 0)))
    assert red["colorfulness"] > grey["colorfulness"]
    assert red["saturation"] > grey["saturation"]


def test_brightness_tracks_luma(tmp_path):
    dark = frame_stats(_solid(tmp_path, "d.png", (10, 10, 10)))
    light = frame_stats(_solid(tmp_path, "l.png", (240, 240, 240)))
    assert dark["brightness"] < light["brightness"]


def test_aggregate_is_median_per_key():
    stats = [{k: 1.0 for k in KEYS}, {k: 3.0 for k in KEYS}, {k: 100.0 for k in KEYS}]
    agg = _aggregate(stats)
    assert all(agg[k] == 3.0 for k in KEYS)      # median, not the 34.67 mean


def test_aggregate_of_nothing_is_empty():
    assert _aggregate([]) == {}


def test_compare_flags_a_flat_frame():
    ours = {"contrast": 20.0, "colorfulness": 20.0, "edge_density": 10.0}
    rivals = {"contrast": 60.0, "colorfulness": 60.0, "edge_density": 30.0}
    notes = compare(ours, rivals)
    assert any("contrast" in n for n in notes)
    assert any("flatter/duller" in n for n in notes)


def test_compare_is_quiet_when_within_norm():
    ours = {"contrast": 55.0, "colorfulness": 58.0, "edge_density": 29.0}
    rivals = {"contrast": 60.0, "colorfulness": 60.0, "edge_density": 30.0}
    assert compare(ours, rivals) == []


def test_compare_flags_an_overbusy_frame():
    ours = {"contrast": 60.0, "colorfulness": 60.0, "edge_density": 90.0}
    rivals = {"contrast": 60.0, "colorfulness": 60.0, "edge_density": 30.0}
    notes = compare(ours, rivals)
    assert any("busier" in n for n in notes)


def test_compare_ignores_missing_baseline_keys():
    assert compare({"contrast": 10.0}, {}) == []


def test_letterbox_crop_takes_the_centre_of_a_16x9_frame():
    """YouTube pads a Short's thumbnail to 16:9 with a darkened blurred copy of
    the frame. Measuring that fill invalidates any comparison, so it is cropped."""
    from PIL import Image

    from carshorts.firstframe import crop_vertical_content
    img = Image.new("RGB", (1280, 720), (0, 0, 0))
    out = crop_vertical_content(img)
    assert out.size == (405, 720)                 # 720 * 9/16, centred


def test_letterbox_crop_is_a_noop_on_vertical_frames(tmp_path):
    from PIL import Image

    from carshorts.firstframe import crop_vertical_content
    img = Image.new("RGB", (1080, 1920), (0, 0, 0))
    assert crop_vertical_content(img).size == (1080, 1920)


def test_crop_removes_the_dark_fill_from_measurement(tmp_path):
    """A bright vertical centre inside a dark fill must measure as BRIGHT."""
    from PIL import Image

    img = Image.new("RGB", (1280, 720), (10, 10, 10))          # dark fill
    img.paste(Image.new("RGB", (405, 720), (240, 240, 240)),    # bright content
              ((1280 - 405) // 2, 0))
    p = tmp_path / "letterboxed.png"
    img.save(p)

    cropped = frame_stats(p)                       # default strips the fill
    raw = frame_stats(p, strip_letterbox=False)
    assert cropped["brightness"] > 200             # sees the real frame
    assert raw["brightness"] < 100                 # fill dominates
    assert cropped["brightness"] > raw["brightness"]
