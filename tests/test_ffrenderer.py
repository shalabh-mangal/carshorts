"""Offline tests for the ffmpeg filter-graph builder (no ffmpeg run).

The graph is built as a pure string, so its structure can be checked exactly:
one filter chain per cut, the right number of concat inputs, opener undarkened,
video vs still handled differently, and cut durations derived from the gaps
between successive starts.
"""
from carshorts.adapters.ffrenderer import (
    _is_video,
    build_scene_filter,
    input_args,
)


def test_is_video_by_extension():
    assert _is_video("a/b/clip.mp4") and _is_video("X.MOV")
    assert not _is_video("photo.jpg") and not _is_video("photo.PNG")


def test_durations_come_from_gaps_between_starts():
    cuts = [(0.0, "a.jpg"), (3.0, "b.jpg"), (5.5, "c.jpg")]
    g = build_scene_filter(cuts, total=8.0)
    assert g["durations"] == [3.0, 2.5, 2.5]      # last runs to `total`


def test_one_chain_and_input_per_cut():
    cuts = [(0.0, "a.jpg"), (2.0, "b.mp4"), (4.0, "c.jpg")]
    g = build_scene_filter(cuts, total=6.0)
    assert len(g["inputs"]) == 3
    assert g["filter"].count("concat=n=3") == 1
    for j in range(3):
        assert f"[v{j}]" in g["filter"]


def test_opener_is_not_darkened_but_later_stills_are():
    cuts = [(0.0, "opener.jpg"), (2.0, "second.jpg")]
    g = build_scene_filter(cuts, total=4.0)
    # opener chain has no brightness reduction; the second one does
    first_chain = g["filter"].split(";")[0]
    second_chain = g["filter"].split(";")[1]
    assert "eq=brightness" not in first_chain
    assert "eq=brightness=-0.350" in second_chain


def test_video_cut_uses_cover_crop_not_zoompan():
    cuts = [(0.0, "a.jpg"), (2.0, "clip.mp4")]
    g = build_scene_filter(cuts, total=4.0)
    chains = g["filter"].split(";")
    assert "zoompan" in chains[0]              # still
    assert "zoompan" not in chains[1]          # video
    assert "crop=1080:1920" in chains[1]


def test_landscape_video_cut_gets_blurpad_not_cover_crop():
    cuts = [(0.0, "a.jpg"), (2.0, "phone_16x9.mp4")]
    g = build_scene_filter(cuts, total=4.0,
                           landscape_paths=frozenset({"phone_16x9.mp4"}))
    chains = g["filter"].split(";")
    video = " ".join(chains)
    assert "boxblur" in video
    assert "overlay=(W-w)/2:(H-h)/2" in video
    assert "force_original_aspect_ratio=decrease" in video
    # the full-clip foreground must stay, not a middle-only crop
    assert "[bp]trim=duration=2.000" in video


def test_portrait_video_cut_stays_cover_crop():
    cuts = [(0.0, "portrait.mp4")]
    g = build_scene_filter(cuts, total=4.0,
                           landscape_paths=frozenset({"phone_16x9.mp4"}))
    assert "boxblur" not in g["filter"]
    assert "crop=1080:1920" in g["filter"]


def test_every_third_video_cut_speed_ramps():
    # j==2 is the 3rd cut -> speed ramp in the moviepy path
    cuts = [(0.0, "a.mp4"), (2.0, "b.mp4"), (4.0, "c.mp4"), (6.0, "d.mp4")]
    g = build_scene_filter(cuts, total=8.0)
    chains = g["filter"].split(";")
    assert "setpts=PTS/1.15" in chains[2]
    assert "setpts=PTS/1.15" not in chains[0]


def test_ken_burns_modes_rotate_by_index():
    cuts = [(i * 2.0, f"s{i}.jpg") for i in range(4)]
    g = build_scene_filter(cuts, total=8.0)
    chains = g["filter"].split(";")
    # mode 0 & 1 are centred zooms; 2 & 3 are pans at fixed 1.12
    assert "z='min(zoom+0.0021,1.10)'" in chains[0]      # zoom in
    assert "max(zoom-0.0021,1.00)" in chains[1]          # zoom out
    assert "z=1.12" in chains[2] and "z=1.12" in chains[3]  # pans


def test_input_args_loop_flags():
    args = input_args(["a.jpg", "b.mp4"])
    assert "-loop" in args                    # still
    assert "-stream_loop" in args             # video
    assert args.count("-i") == 2


def test_empty_cuts_is_safe():
    g = build_scene_filter([], total=0.0)
    assert g["inputs"] == [] and g["filter"] == ""
