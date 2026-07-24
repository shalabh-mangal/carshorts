"""Offline tests for the ffmpeg overlay command builder (no ffmpeg run).

The layers themselves are baked with PIL (covered indirectly by the render
verification); here we lock the pure command construction: one input + one
timed overlay per layer, correct enable windows, audio mux with/without music,
and the %03d pattern derivation for sequence layers.
"""
from carshorts.adapters.ffoverlay import _pattern, build_overlay_command


def _static(start, end, png="hold.png"):
    return {"frames": [png], "fps": None, "start": start, "end": end}


def _seq(start, end, n=3, fps=24):
    return {"frames": [f"seq_a{i:03d}.png" for i in range(n)],
            "fps": fps, "start": start, "end": end}


def test_pattern_derivation():
    assert _pattern(["card_0_4_s000.png", "card_0_4_s001.png"]) == "card_0_4_s%03d.png"
    assert _pattern(["x_a000.png"]) == "x_a%03d.png"


def test_one_input_and_overlay_per_layer():
    layers = [_static(1.0, 3.0), _seq(4.0, 5.0)]
    cmd = build_overlay_command("base.mp4", layers, ["voice.m4a"], "out.mp4")
    # base + 2 layers + voice = 4 inputs
    assert cmd.count("-i") == 4
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert graph.count("overlay=0:0") == 2


def test_voice_segments_are_concatenated():
    cmd = build_overlay_command("base.mp4", [_static(1, 2)],
                                ["a.mp3", "b.mp3", "c.mp3"], "out.mp4")
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert "concat=n=3:v=0:a=1" in graph
    assert cmd.count("-i") == 1 + 1 + 3           # base + 1 layer + 3 voice


def test_enable_windows_match_layer_times():
    layers = [_static(2.5, 6.25)]
    cmd = build_overlay_command("base.mp4", layers, ["voice.m4a"], "out.mp4")
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert "between(t,2.500,6.250)" in graph


def test_static_layer_loops_sequence_layer_uses_framerate():
    cmd = build_overlay_command("base.mp4", [_static(1, 2), _seq(3, 4, fps=34)],
                                "voice.m4a", "out.mp4")
    assert "-loop" in cmd            # static
    assert "-framerate" in cmd       # sequence
    assert "34" in cmd


def test_music_is_mixed_and_ducked_when_present():
    cmd = build_overlay_command("base.mp4", [_static(1, 2)], "voice.m4a",
                                "out.mp4", music_path="bed.mp3", music_gain=0.12)
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert "volume=0.12" in graph and "amix=inputs=2" in graph


def test_no_music_maps_voice_directly():
    cmd = build_overlay_command("base.mp4", [_static(1, 2)], ["voice.m4a"], "out.mp4")
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert "amix" not in graph
    # voice is the last input; mapped straight to audio out
    assert cmd.count("-map") == 2


def test_total_bounds_output_when_given():
    cmd = build_overlay_command("base.mp4", [_static(1, 2)], ["v.m4a"], "out.mp4",
                                total=61.6)
    assert "-t" in cmd and "61.600" in cmd


def test_no_layers_maps_base_video_directly():
    cmd = build_overlay_command("base.mp4", [], ["v.m4a"], "out.mp4")
    assert "-map" in cmd
    mi = cmd.index("-map")
    assert cmd[mi + 1] == "0:v"
