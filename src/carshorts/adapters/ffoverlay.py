"""ffmpeg overlay compositing — the rest of the fast path (increment 2).

The hybrid (ffbase) still let moviepy composite overlays over the full 62s,
which was the remaining bottleneck. This bakes each overlay into small assets
and lets ffmpeg place them, so moviepy never touches the full timeline.

Overlays must stay IDENTICAL (owner requirement), so this reuses the renderer's
exact PIL generators (_overlay_png / _countup_frames / _lss_strip_png /
_wipe_bar_frames) and the exact easing (_settle_scale / _slam_scale). Each
overlay frame is composited onto a FULL 1080x1920 transparent canvas at the
same position moviepy uses, so ffmpeg only needs `overlay=0:0` with an `enable`
window — no x/y or scale maths on the ffmpeg side, nothing to drift.

A `layer` is: a list of full-frame RGBA PNGs + the fps they play at + the
absolute [start, end] window. One PNG = a static hold (looped); many = an
animated entrance (settle / slam) or a content sequence (count-up / wipe).
build_overlay_command() turns layers into a single ffmpeg invocation and is a
pure function (unit-tested; no ffmpeg run).
"""
from __future__ import annotations

import math

from .renderer import (
    TEXT_WHITE,
    _countup_frames,
    _lss_strip_png,
    _overlay_png,
    _settle_scale,
    _slam_scale,
    _wipe_bar_frames,
)

SETTLE_DUR = 0.22   # _settle_scale returns 1.0 at/after this
SLAM_DUR = 0.15     # _slam_scale returns 1.0 at/after this


def _blit(src_png: str, scale: float, top_px: int, size, out_png: str) -> str:
    """Composite src_png (optionally scaled) onto a full transparent frame,
    centred horizontally with its TOP at top_px — matching moviepy's
    with_position(("center", top_px)) + resized(scale)."""
    from PIL import Image

    w, h = size
    im = Image.open(src_png).convert("RGBA")
    if abs(scale - 1.0) > 1e-3:
        im = im.resize((max(1, round(im.width * scale)),
                        max(1, round(im.height * scale))), Image.LANCZOS)
    frame = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    frame.alpha_composite(im, ((w - im.width) // 2, int(top_px)))
    frame.save(out_png)
    return out_png


def _anim_layer(src_png: str, scale_fn, anim_dur: float, top_px: int, size,
                fps: int, tdir: str, tag: str, start: float) -> dict:
    """Bake an entrance animation (settle/slam) as full-frame frames."""
    n = max(1, math.ceil(anim_dur * fps))
    frames = []
    for i in range(n):
        s = scale_fn(i / fps)
        frames.append(_blit(src_png, s, top_px, size,
                            f"{tdir}/{tag}_a{i:03d}.png"))
    return {"frames": frames, "fps": fps, "start": start,
            "end": start + n / fps}


def _seq_layer(src_frames: list[str], seq_fps: int, top_px: int, size,
               tdir: str, tag: str, start: float) -> dict:
    """Bake a content sequence (count-up / wipe) as full-frame frames."""
    frames = [_blit(f, 1.0, top_px, size, f"{tdir}/{tag}_s{i:03d}.png")
              for i, f in enumerate(src_frames)]
    return {"frames": frames, "fps": seq_fps, "start": start,
            "end": start + len(frames) / seq_fps}


def _static_layer(src_png: str, scale: float, top_px: int, size, tdir: str,
                  tag: str, start: float, end: float) -> dict | None:
    if end <= start + 1e-3:
        return None
    png = _blit(src_png, scale, top_px, size, f"{tdir}/{tag}_hold.png")
    return {"frames": [png], "fps": None, "start": start, "end": end}


def build_layers(sections, durations, size, fps: int, tdir: str) -> list[dict]:
    """Bake every word-pop across all sections into full-frame overlay layers.

    Mirrors renderer.render_sections' word_pops block exactly (same generators,
    positions, easings, start/dur maths), so the composited result is identical.
    """
    _w, h = size
    y_top = int(h * 0.30)
    y_rail = int(h * 0.64)
    layers: list[dict] = []
    cursor = 0.0
    for k, (section, dur) in enumerate(zip(sections, durations)):
        for pi, pop in enumerate(section.word_pops):
            pop_start, pop_dur, pop_text = pop[0], pop[1], pop[2]
            kind = pop[3] if len(pop) > 3 else (
                "number" if any(c.isdigit() for c in pop_text) else "word")
            label = pop[4] if len(pop) > 4 else ""
            start = cursor + pop_start
            show_dur = (pop_dur if kind == "reaction"
                        else min(pop_dur, dur - pop_start))
            end = start + show_dur
            tag = f"{k}_{pi}"

            if kind == "card":
                src = _countup_frames(pop_text, label, tdir, f"card_{tag}")
                seq = _seq_layer(src, 24, y_top, size, tdir, f"card_{tag}", start)
                layers.append(seq)
                hold = _static_layer(src[-1], 1.0, y_top, size, tdir,
                                     f"card_{tag}", seq["end"], max(seq["end"] + 0.7, end))
                if hold:
                    layers.append(hold)
            elif kind in ("reaction", "lss"):
                if kind == "reaction":
                    src = _overlay_png(pop_text.upper(), 110, TEXT_WHITE,
                                       f"{tdir}/rx_{tag}.png", fit_one_line=True)
                else:
                    src = _lss_strip_png(f"{tdir}/lss_{tag}.png")
                layers.append(_anim_layer(src, _slam_scale, SLAM_DUR, y_top,
                                          size, fps, tdir, tag, start))
                hold = _static_layer(src, 1.0, y_top, size, tdir, tag,
                                     start + SLAM_DUR, end)
                if hold:
                    layers.append(hold)
            else:  # word / number, on the rail with settle easing
                src = _overlay_png(pop_text.upper(), 96, TEXT_WHITE,
                                   f"{tdir}/pop_{tag}.png",
                                   accent_digits=(kind == "number"))
                layers.append(_anim_layer(src, _settle_scale, SETTLE_DUR, y_rail,
                                          size, fps, tdir, tag, start))
                hold = _static_layer(src, 1.0, y_rail, size, tdir, tag,
                                     start + SETTLE_DUR, end)
                if hold:
                    layers.append(hold)
                if kind == "number":
                    from PIL import Image as _I
                    pw = _I.open(src).width
                    ph = _I.open(src).height
                    bar_w = min(pw - 90, max(140, pw // 3))
                    bar_top = y_rail + ph - 8
                    bframes = _wipe_bar_frames(bar_w, tdir, f"bar_{tag}")
                    wl = _seq_layer(bframes, 34, bar_top, size, tdir, f"bar_{tag}", start)
                    layers.append(wl)
                    bhold = _static_layer(bframes[-1], 1.0, bar_top, size, tdir,
                                          f"bar_{tag}", wl["end"], end)
                    if bhold:
                        layers.append(bhold)
        cursor += dur
    return layers


def build_overlay_command(base_path: str, layers: list[dict],
                          voice_segments: list[str], out_path: str,
                          music_path: str | None = None,
                          music_gain: float = 0.12, total: float | None = None,
                          fps: int = 24, threads: int | None = None) -> list[dict]:
    """Pure builder: return the ffmpeg argv that composites base + all overlay
    layers + the concatenated voice segments (+ music) into out_path.

    The voice is concatenated by ffmpeg from the per-section audio files —
    moviepy's own audio writer was throwing broken-pipe on Windows, and doing it
    in the one composite pass is both robust and avoids an extra encode. No
    ffmpeg is run here."""
    import os

    inputs: list[str] = ["-i", base_path]          # 0:v base
    idx = 1
    filt: list[str] = []
    last = "0:v"
    for li, layer in enumerate(layers):
        if len(layer["frames"]) == 1:
            # static hold: constant image, gated by enable
            inputs += ["-loop", "1", "-i", layer["frames"][0]]
        else:
            pattern = _pattern(layer["frames"])
            inputs += ["-framerate", str(layer["fps"]), "-i", pattern]
        # shift this input so its frame 0 lands at layer.start, then overlay
        # only within [start, end]
        s, e = layer["start"], layer["end"]
        lab_in = f"{idx}:v"
        pts = f"[{lab_in}]setpts=PTS-STARTPTS+{s:.3f}/TB[l{li}]"
        filt.append(pts)
        out = f"o{li}"
        filt.append(f"[{last}][l{li}]overlay=0:0:enable='between(t,{s:.3f},{e:.3f})'"
                    f":eof_action=pass[{out}]")
        last = out
        idx += 1

    vmap = f"[{last}]" if layers else "0:v"

    # audio: concat the section voice segments (resampled to a common format so
    # concat never errors), then optionally mix ducked music under it
    voice_labels = []
    for si, seg in enumerate(voice_segments):
        inputs += ["-i", seg]
        filt.append(f"[{idx}:a]aformat=sample_rates=44100:channel_layouts=stereo"
                    f"[va{si}]")
        voice_labels.append(f"[va{si}]")
        idx += 1
    filt.append("".join(voice_labels)
                + f"concat=n={len(voice_labels)}:v=0:a=1[voice]")

    if music_path:
        inputs += ["-stream_loop", "-1", "-i", music_path]
        music_lab = f"{idx}:a"
        idx += 1
        filt.append(f"[{music_lab}]aformat=sample_rates=44100:channel_layouts=stereo,"
                    f"volume={music_gain}[m]")
        filt.append("[voice][m]amix=inputs=2:duration=first:normalize=0[aout]")
        amap = "[aout]"
    else:
        amap = "[voice]"

    cmd = ["ffmpeg", "-y", *inputs,
           "-filter_complex", ";".join(filt),
           "-map", vmap, "-map", amap]
    if total:
        cmd += ["-t", f"{total:.3f}"]
    cmd += ["-r", str(fps), "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
            "-threads", str(threads or os.cpu_count() or 4), out_path]
    return cmd


def _pattern(frames: list[str]) -> str:
    """image2 needs a %03d pattern; our bakers already number frames a000/s000.
    Return the pattern by replacing the trailing NNN before .png."""
    import re
    first = frames[0]
    return re.sub(r"(\d{3})(\.png)$", r"%03d\2", first)
