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

from carshorts.core import paths

VERTICAL = (1080, 1920)
_VIDEO_EXT = (".mp4", ".mov", ".m4v", ".webm")


def _is_video(path: str) -> bool:
    return path.lower().endswith(_VIDEO_EXT)


def _cover_scale_crop(w: int, h: int) -> str:
    """Scale to fully cover WxH then centre-crop — the filter form of
    renderer._cover_crop. force_original_aspect_ratio=increase guarantees cover."""
    return (f"scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h}")


def _smart_cover_crop(w: int, h: int, fc: float, lift: bool = False) -> str:
    """Subject-aware cover-crop: scale to cover, then crop the WxH window centred
    on the subject (fc = subject centre as a fraction of source width, found by a
    saliency probe) instead of blind centre. Keeps the car in frame and full-bleed.
    The x expression clamps to the pannable range so it never reads outside the
    frame; commas are escaped for the filtergraph parser."""
    x = f"max(0\\,min(iw-ow\\,iw*{fc:.4f}-ow/2))"
    chain = (f"scale={w}:{h}:force_original_aspect_ratio=increase,"
             f"crop={w}:{h}:x={x}:y=0,setsar=1")
    if lift:   # opener exposure/saturation nudge to the feed norm (matches blurpad)
        chain += ",eq=brightness=0.06:saturation=1.15"
    return chain


def _blurpad_landscape(w: int, h: int, label: str, lift: bool = False) -> str:
    """Landscape footage in a vertical frame: blurred cover-fill background with
    the FULL clip visible, centered. The classic Shorts treatment — cover-crop
    alone keeps only the middle band, blowing the subject up huge.
    Returns a complete multi-chain graph ending at [label]."""
    fg_scale = f"scale={w}:{h}:force_original_aspect_ratio=decrease"
    # The bg fill is never darkened: eq brightness is an ADDITIVE shift, so it
    # clips already-dim source rows (dusk skies etc.) to black. `lift` (opener
    # only) is a gentle exposure+saturation boost so frame 0 reaches the feed
    # norm — the QA gate treats exposure as ours to control.
    bg_fx = ",eq=brightness=0.09:saturation=1.25" if lift else ""
    return (f"split[bgb][fg];"
            f"[bgb]{_cover_scale_crop(w, h)},boxblur=24:2{bg_fx}[bgb];"
            f"[fg]{fg_scale},setsar=1[fg];"
            f"[bgb][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[{label}]")


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


def _video_cut(w: int, h: int, dur: float, speed_ramp: bool,
               landscape: bool = False, lift: bool = False) -> str:
    """A stock/own video cut: cover-crop, or blur-pad for landscape footage so
    the whole clip is visible (no giant middle crop); silence handled at stream
    level; optional 1.15x speed ramp (every 3rd cut in the moviepy path).

    Returns the chain from the cut's input stream up to (not including) the
    output label — the caller appends [label] and the trim/fps stages.
    For blur-pad the chain itself terminates the graph at [bp]."""
    if landscape:
        return _blurpad_landscape(w, h, "bp", lift=lift)
    chain = _cover_scale_crop(w, h)
    if speed_ramp:
        chain += ",setpts=PTS/1.15"
    chain += ",setsar=1"
    return chain


def build_scene_filter(cuts: list[tuple[float, str]], total: float,
                       size: tuple[int, int] = VERTICAL, fps: int = 24,
                       no_darken=frozenset({0}),
                       landscape_paths: frozenset[str] | None = None,
                       framing: dict | None = None) -> dict:
    """Build the filter_complex for a base scene from timed cuts.

    cuts = [(start_seconds, asset_path), ...] on the GLOBAL timeline; total is
    the video duration. `no_darken` is the set of cut indices to leave at full
    brightness — the opener (0) always, plus the loop-close flash if appended,
    so the flash matches the opener it loops back to.

    `framing` is the ADAPTIVE decision per path (from the saliency probe):
    {path: ("crop", fc)} for subject-aware full-bleed cover-crop, or
    {path: ("blurpad", None)} for the clean blurred-pillarbox fallback (subject
    too wide to fit a 9:16 window without losing relevance). `landscape_paths`
    is the legacy fallback (all-blurpad) when no framing dict is supplied.
    Pure function — computes no saliency, runs no ffmpeg.
    """
    landscape = landscape_paths or frozenset()
    framing = framing or {}
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
            decision = framing.get(path)
            if decision is None and path in landscape:
                decision = ("blurpad", None)   # legacy path: all landscape -> blurpad
            mode = decision[0] if decision else "cover"
            ct = decision[2] if decision and len(decision) > 2 else 0.0
            cb = decision[3] if decision and len(decision) > 3 else 0.0
            # strip baked-in cinematic letterbox before framing (2.39:1 in a 16:9 file)
            pre = (f"crop=iw:ih*{1 - ct - cb:.4f}:0:ih*{ct:.4f},"
                   if (ct + cb) > 0.02 else "")
            if mode == "blurpad":
                graph = f"[{j}:v]{pre}"
                graph += _video_cut(w, h, dur, speed_ramp=False,
                                    landscape=True, lift=(j in no_darken))
                parts.append(f"{graph};[bp]trim=duration={dur:.3f},fps={fps},"
                             f"setpts=PTS-STARTPTS[v{j}]")
            elif mode == "crop":
                chain = _smart_cover_crop(w, h, decision[1], lift=(j in no_darken))
                parts.append(f"[{j}:v]{pre}{chain},trim=duration={dur:.3f},fps={fps},"
                             f"setpts=PTS-STARTPTS[v{j}]")
            else:
                chain = _video_cut(w, h, dur, speed_ramp=(j % 3 == 2))
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
    subject = manifest.get("subject", "")
    slug = ""
    if subject:
        import re
        slug = re.sub(r"[^a-z0-9]+", "-", subject.lower()).strip("-")
    car = paths.car_dir(slug)
    search_dirs = [
        car / "images", car / "press", car / "stock", car / "own",
        paths.STOCK,
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


def _probe_framing(paths_list: list[str], frame_w: int, frame_h: int) -> dict:
    """ADAPTIVE framing decision per landscape clip (subject-aware, from research).

    A landscape (16:9-ish) clip can't fill a 9:16 frame without either cropping
    the sides or shrinking into a pillarbox. We sample a few frames, find the
    subject by COLOURFULNESS (the vivid car pops against muted sky/sand/road —
    far more reliable than edges, which textured ground fools), and:
      - if the subject fits the crop window -> ("crop", fc) subject-aware cover-crop
        centred on it (full-bleed, keeps the car);
      - else -> ("blurpad", None) clean pillarbox (keeps the WHOLE car, no clip).
    One decision per clip (averaged over sampled frames) so the crop never jitters.
    Any probe failure defaults to blurpad — the safe, never-clips choice."""
    import subprocess
    import tempfile

    import numpy as np
    from PIL import Image

    crop_frac = (frame_w / frame_h) / (16 / 9)   # width kept by a 9:16 cover-crop
    out: dict = {}
    for p in dict.fromkeys(paths_list):
        if not _is_video(p):
            continue
        try:
            pr = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "v:0",
                 "-show_entries", "stream=width,height:format=duration",
                 "-of", "json", p], capture_output=True, text=True, timeout=20)
            import json as _json
            meta = _json.loads(pr.stdout)
            st = meta.get("streams", [{}])[0]
            sw, sh = int(st.get("width", 0)), int(st.get("height", 0))
            dur = float(meta.get("format", {}).get("duration", 0) or 0)
            if not (sw and sh and sw / sh > frame_w / frame_h):
                continue                       # portrait/near-square -> normal cover
            energy = None
            bars_top, bars_bot = [], []
            for ft in (0.15, 0.4, 0.6, 0.85):
                t = max(0.0, ft * dur)
                tmp = tempfile.mktemp(suffix=".jpg")
                subprocess.run(["ffmpeg", "-y", "-ss", f"{t:.2f}", "-i", p,
                                "-frames:v", "1", "-vf", "scale=480:-1", tmp],
                               capture_output=True, timeout=20)
                try:
                    arr = np.asarray(Image.open(tmp).convert("HSV")).astype(float)
                except Exception:  # noqa: BLE001 — a missing sample is skipped
                    continue
                e = (arr[:, :, 1] / 255.0 * (arr[:, :, 2] / 255.0)).sum(axis=0)
                energy = e if energy is None else energy + e
                # baked-in letterbox: rows near-black across the width (cinematic
                # 2.39:1 content inside a 16:9 file) — measure so we can strip them
                rowv = arr[:, :, 2].mean(axis=1)
                hpx = len(rowv)
                tb = 0
                while tb < hpx and rowv[tb] < 18:
                    tb += 1
                bb = 0
                while bb < hpx and rowv[hpx - 1 - bb] < 18:
                    bb += 1
                bars_top.append(tb / hpx)
                bars_bot.append(bb / hpx)
            if energy is None:
                out[p] = ("blurpad", None, 0.0, 0.0)
                continue
            # crop only bars present in EVERY sample (min) so a legitimately dark
            # frame never causes over-cropping; ignore tiny/huge detections
            ct = min(bars_top) if bars_top else 0.0
            cb = min(bars_bot) if bars_bot else 0.0
            if ct + cb < 0.02 or ct + cb > 0.30:
                ct = cb = 0.0
            energy = np.convolve(energy, np.ones(15) / 15, mode="same")
            # Isolate the SUBJECT: subtract the diffuse background level (warm sand/
            # sky carry saturation across the whole width and would otherwise read
            # as "car"). What remains as a peak is the vivid car.
            strong = np.clip(energy - np.percentile(energy, 60), 0.0, None)
            if strong.sum() < 1e-6:
                strong = energy
            n = len(strong)
            centroid = float((strong * np.arange(n)).sum() / (strong.sum() + 1e-6))
            fc = centroid / n
            win = crop_frac * n                       # crop window width in columns
            lo = int(max(0, round(centroid - win / 2)))
            hi = int(min(n, round(centroid + win / 2)))
            fit = float(strong[lo:hi].sum() / (strong.sum() + 1e-6))
            # fits when most of the subject sits inside the crop window; else the
            # car is too wide to crop without losing its nose/tail -> pillarbox
            mode = "crop" if fit >= 0.80 else "blurpad"
            out[p] = (mode, fc if mode == "crop" else None, ct, cb)
        except Exception:  # noqa: BLE001 — never let framing analysis break a render
            out[p] = ("blurpad", None, 0.0, 0.0)
    return out


def render_base_from_cuts(cuts, total: float, out_path: str, fps: int = 24,
                          size=VERTICAL, threads: int | None = None,
                          no_darken=frozenset({0})) -> str:
    """Assemble the base scene (cuts + motion, no overlays/audio) in one ffmpeg
    pass. Returns out_path; raises RuntimeError with ffmpeg's tail on failure."""
    import os
    import subprocess

    framing = _probe_framing([p for _, p in cuts], *size)
    graph = build_scene_filter(cuts, total, size=size, fps=fps,
                               no_darken=no_darken, framing=framing)
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
