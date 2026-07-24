"""ffmpeg-native scene assembly — the fast path (experimental, opt-in).

moviepy composites every frame in pure Python: a 62s Short costs ~11 min on a
CPU-only box, and that render time IS the learning-loop latency. The dominant
cost is the per-frame work — Ken Burns re-resizing each still every frame, and
layer compositing — none of which is parallel.

ffmpeg does the same work in C, multithreaded. This module builds a single
`-filter_complex` graph that reproduces the BASE scene (the cut sequence with
Ken Burns / punch-in motion), which is the expensive part. Overlays stay a
later increment; this proves the concept and the speedup first.

Design so it can be trusted:
  - build_scene_filter() is PURE (inputs -> filtergraph string). No I/O, no
    ffmpeg, fully unit-tested offline. The command that renders is assembled
    from it separately.
  - Motion mirrors renderer._sub_visual: stills alternate zoom-in / zoom-out /
    pan by cut index (j % 4); video cuts get a micro punch-in. Same 1080x1920,
    same cover-fill-then-move, same j-based rotation, so cuts line up with the
    moviepy version for A/B comparison.
"""
from __future__ import annotations

from pathlib import Path

VERTICAL = (1080, 1920)
_VIDEO_EXT = (".mp4", ".mov", ".m4v", ".webm")


def _is_video(path: str) -> bool:
    return path.lower().endswith(_VIDEO_EXT)


def _cover_scale_crop(w: int, h: int) -> str:
    """Scale to fully cover WxH then centre-crop — the filter form of
    renderer._cover_crop. force_original_aspect_ratio=increase guarantees cover."""
    return (f"scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h}")


def _kenburns_still(idx: int, frames: int, w: int, h: int, fps: int,
                    darken: float) -> str:
    """Ken Burns for one still, chosen by cut index exactly as _sub_visual does:
      0 zoom-in 1.00->1.10   1 zoom-out 1.10->1.00
      2 pan-left @1.12       3 pan-right @1.12
    zoompan is fed a frame already cover-scaled to WxH, then moves within it.
    We upscale 2x first so zoompan's integer-pixel stepping stays smooth."""
    mode = idx % 4
    d = max(1, frames)
    # zoompan quirk: operate on an enlarged canvas so sub-pixel zoom isn't jerky
    pre = f"{_cover_scale_crop(w, h)},scale={w * 2}:{h * 2}"
    zc = "'min(zoom+0.0021,1.10)'"          # ~ +0.10 across a typical cut
    if mode == 0:      # zoom in, centred
        z = zc
        x = "'iw/2-(iw/zoom/2)'"
        y = "'ih/2-(ih/zoom/2)'"
    elif mode == 1:    # zoom out, centred (start zoomed, relax)
        z = "'if(eq(on,0),1.10,max(zoom-0.0021,1.00))'"
        x = "'iw/2-(iw/zoom/2)'"
        y = "'ih/2-(ih/zoom/2)'"
    elif mode == 2:    # pan left at fixed 1.12
        z = "1.12"
        x = "'(iw-iw/zoom)*(1-on/max(1,D-1))'"
        y = "'ih/2-(ih/zoom/2)'"
    else:              # pan right at fixed 1.12
        z = "1.12"
        x = "'(iw-iw/zoom)*(on/max(1,D-1))'"
        y = "'ih/2-(ih/zoom/2)'"
    zp = (f"zoompan=z={z}:x={x}:y={y}:d={d}:s={w}x{h}:fps={fps}"
          .replace("D", str(d)))
    chain = f"{pre},{zp},setsar=1"
    if darken > 0:
        # blend toward black == reduce luma; eq brightness shift matches a
        # 0.35 alpha black overlay closely enough for the base pass
        chain += f",eq=brightness={-darken:.3f}"
    return chain


def _video_cut(w: int, h: int, dur: float, speed_ramp: bool) -> str:
    """A stock/own video cut: cover-crop, silence handled at stream level,
    optional 1.15x speed ramp (every 3rd cut in the moviepy path)."""
    chain = _cover_scale_crop(w, h)
    if speed_ramp:
        chain += ",setpts=PTS/1.15"
    chain += ",setsar=1"
    return chain


def build_scene_filter(cuts: list[tuple[float, str]], total: float,
                       size: tuple[int, int] = VERTICAL, fps: int = 24,
                       no_darken=frozenset({0})) -> dict:
    """Build the filter_complex for a base scene from timed cuts.

    cuts = [(start_seconds, asset_path), ...] on the GLOBAL timeline; total is
    the video duration. `no_darken` is the set of cut indices to leave at full
    brightness — the opener (0) always, plus the loop-close flash if appended,
    so the flash matches the opener it loops back to. Returns everything the
    caller needs to run ffmpeg, but runs no ffmpeg.
    """
    w, h = size
    if not cuts:
        return {"inputs": [], "filter": "", "map": "", "durations": []}

    # each cut runs until the next cut's start (last until `total`)
    spans = []
    for j, (start, path) in enumerate(cuts):
        end = cuts[j + 1][0] if j + 1 < len(cuts) else total
        spans.append((path, max(0.1, end - start)))

    inputs: list[str] = []
    parts: list[str] = []
    labels: list[str] = []
    for j, (path, dur) in enumerate(spans):
        frames = max(1, round(dur * fps))
        if _is_video(path):
            # loop a short clip to fill the cut; trim to exact frames
            inputs.append(path)
            chain = _video_cut(w, h, dur, speed_ramp=(j % 3 == 2))
            # trim to duration and normalise timebase/fps
            parts.append(f"[{j}:v]{chain},trim=duration={dur:.3f},fps={fps},"
                         f"setpts=PTS-STARTPTS[v{j}]")
        else:
            inputs.append(path)
            # opener (and the loop-close flash) are not darkened
            darken = 0.0 if j in no_darken else 0.35
            chain = _kenburns_still(j, frames, w, h, fps, darken)
            parts.append(f"[{j}:v]{chain},trim=duration={dur:.3f},"
                         f"setpts=PTS-STARTPTS[v{j}]")
        labels.append(f"[v{j}]")

    concat = "".join(labels) + f"concat=n={len(labels)}:v=1:a=0[vout]"
    parts.append(concat)
    return {"inputs": inputs, "filter": ";".join(parts), "map": "[vout]",
            "durations": [d for _, d in spans]}


def global_cuts_from_manifest(manifest: dict) -> tuple[list, float]:
    """Reconstruct the GLOBAL (whole-video) cut timeline from a render manifest.

    The manifest stores cuts per section at section-relative times; sections play
    back to back, so a cut's global start is (sum of earlier section durations)
    + its local t. Returns (cuts, total_duration) resolving asset FILENAMES to
    real paths under the car's pools.
    """
    import json
    from pathlib import Path as _P

    subject = manifest.get("subject", "")
    slug = ""
    if subject:
        import re
        slug = re.sub(r"[^a-z0-9]+", "-", subject.lower()).strip("-")
    search_dirs = [
        _P(f"assets/cars/{slug}/images"), _P(f"assets/cars/{slug}/press"),
        _P(f"assets/cars/{slug}/stock"), _P(f"assets/cars/{slug}/own"),
        _P("assets/stock"),
    ]
    by_name: dict[str, str] = {}
    for d in search_dirs:
        if d.exists():
            for p in d.iterdir():
                by_name.setdefault(p.name, str(p))

    cuts: list[tuple[float, str]] = []
    offset = 0.0
    for sec in manifest.get("sections", []):
        for c in sec.get("cuts", []):
            path = by_name.get(c["asset"])
            if path:
                cuts.append((offset + c["t"], path))
        offset += sec["duration"]
    return cuts, offset


def global_cuts_from_sections(sections, durations) -> tuple[list, float]:
    """Flatten Section.timed_cuts onto the global timeline, exactly reproducing
    moviepy's per-section timing.

    Each section's cuts are at section-relative offsets; sections play back to
    back, so a cut's global start is (sum of earlier section durations) + its
    local offset. Because every section's first cut sits at offset ~0, running
    each flattened cut until the NEXT cut's global start yields the same spans
    moviepy's _timed_scene produces per section — no drift.
    """
    cuts: list[tuple[float, str]] = []
    offset = 0.0
    for section, dur in zip(sections, durations):
        for t_off, path in section.timed_cuts:
            cuts.append((offset + t_off, path))
        offset += dur
    return cuts, offset


def render_base_from_cuts(cuts, total: float, out_path: str, fps: int = 24,
                          size=VERTICAL, threads: int | None = None,
                          no_darken=frozenset({0})) -> str:
    """Assemble the base scene (cuts + motion, no overlays/audio) in one ffmpeg
    pass. Returns out_path; raises RuntimeError with ffmpeg's tail on failure."""
    import os
    import subprocess

    graph = build_scene_filter(cuts, total, size=size, fps=fps, no_darken=no_darken)
    if not graph["inputs"]:
        raise RuntimeError("no resolvable cuts to render")
    cmd = ["ffmpeg", "-y", *input_args(graph["inputs"]),
           "-filter_complex", graph["filter"], "-map", graph["map"],
           "-t", f"{total:.3f}", "-r", str(fps),
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
           "-pix_fmt", "yuv420p", "-threads", str(threads or os.cpu_count() or 4),
           out_path]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError("ffmpeg base render failed:\n" + proc.stderr[-1200:])
    return out_path


def render_base(manifest_path: str, out_path: str, fps: int = 24,
                threads: int | None = None) -> str:
    """Render a base scene straight from a saved manifest (CLI / A-B use)."""
    import json

    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    cuts, total = global_cuts_from_manifest(manifest)
    return render_base_from_cuts(cuts, total, out_path, fps=fps, threads=threads)


def input_args(inputs: list[str]) -> list[str]:
    """ffmpeg -i args, looping stills/videos so a short source fills its cut.
    Stills use -loop 1; videos -stream_loop -1. Duration is bounded by the
    per-stream trim in the filtergraph."""
    args: list[str] = []
    for path in inputs:
        if _is_video(path):
            args += ["-stream_loop", "-1", "-i", path]
        else:
            args += ["-loop", "1", "-framerate", "24", "-i", path]
    return args
