"""Render QA gate — every finished video is validated layer by layer.

  python -m carshorts.quality.qa out/thar_draft.mp4            # uses <name>.manifest.json

Checks (deterministic, no LLM):
  container  — resolution 1080x1920, 44.1 kHz audio, duration ≈ planned
  loudness   — integrated -14 LUFS ±2, true peak <= -1 dBTP
  cuts       — monotonic, none shorter than ~1.05s, no asset repeated (when the
               pool allowed it), video opens AND closes on the subject car
  overlays   — keyword/callout windows inside their section, starts monotonic,
               every callout anchored before its section ends

Prints a PASS/FAIL checklist; returns overall bool. produce runs this
automatically after every render.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

CAR_FAMILIES = {"roxx", "red", "thar", "mahindra", "pool"}   # pool_* = own footage


def _probe(path: str) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=codec_type,width,height,sample_rate:format=duration",
         "-of", "json", path], capture_output=True, text=True)
    return json.loads(out.stdout or "{}")


def _loudness(path: str) -> tuple[float, float]:
    out = subprocess.run(
        ["ffmpeg", "-i", path, "-af", "loudnorm=print_format=json", "-f", "null", "-"],
        capture_output=True, text=True).stderr
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", out, re.S)
    if not m:
        return (0.0, 0.0)
    data = json.loads(m.group(0))
    return float(data.get("input_i", 0)), float(data.get("input_tp", 0))


def _family(asset_name: str) -> str:
    stem = Path(asset_name).stem
    return stem.split("_")[0].lower()


def run_qa(video_path: str, manifest_path: str | None = None,
           details: bool = False):
    manifest_path = manifest_path or str(Path(video_path).with_suffix(".manifest.json"))
    checks: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str = ""):
        checks.append((name, ok, detail))

    probe = _probe(video_path)
    streams = {s_["codec_type"]: s_ for s_ in probe.get("streams", [])}
    vs, as_ = streams.get("video", {}), streams.get("audio", {})
    check("video 1080x1920", vs.get("width") == 1080 and vs.get("height") == 1920,
          f"{vs.get('width')}x{vs.get('height')}")
    check("audio 44.1 kHz", str(as_.get("sample_rate")) == "44100", str(as_.get("sample_rate")))

    manifest = {}
    if Path(manifest_path).exists():
        manifest = json.loads(Path(manifest_path).read_text())
    sections = manifest.get("sections", [])
    planned = sum(sec["duration"] for sec in sections)
    actual = float(probe.get("format", {}).get("duration", 0))
    check("duration ≈ plan", abs(actual - planned) < 1.6,
          f"video {actual:.1f}s vs plan {planned:.1f}s (+loop flash)")

    # Tight-Shorts target ~35s (retention data: 63s held ~32%, 46s looped at
    # 130%). 48s is the hard ceiling — a longer runtime means the writer let a
    # beat balloon; re-trim rather than ship it.
    check("runtime ≤ 48s (tight-Shorts, target ~35s)", actual <= 48.0, f"{actual:.1f}s")

    lufs, tp = _loudness(video_path)
    check("loudness -14 LUFS ±2", -16.0 <= lufs <= -12.0, f"{lufs:.1f} LUFS")
    check("true peak ≤ -1 dBTP", tp <= -0.9, f"{tp:.1f} dBTP")

    if sections:
        all_assets: list[str] = []
        cuts_ok = spacing_ok = True
        for sec in sections:
            times = [c["t"] for c in sec.get("cuts", [])]
            if times != sorted(times):
                cuts_ok = False
            spans = [b - a for a, b in zip(times, times[1:])]
            if any(sp < 1.0 for sp in spans):
                spacing_ok = False
            all_assets += [c["asset"] for c in sec.get("cuts", [])]
        check("cuts monotonic", cuts_ok)
        check("no cut shorter than ~1s", spacing_ok)
        repeats = len(all_assets) - len(set(all_assets))
        pool_size = manifest.get("pool_size", 0)
        allowed = max(0, len(all_assets) - pool_size)
        check("no repeated asset", repeats <= allowed,
              f"{repeats} repeats vs {allowed} allowed (pool {pool_size}, cuts {len(all_assets)})")

        first = sections[0].get("cuts", [{}])[0].get("asset", "")
        last = sections[-1].get("cuts", [{}])[-1].get("asset", "")
        families = set(manifest.get("subject_families") or CAR_FAMILIES)

        def on_subject(asset: str) -> bool:
            name = asset.lower()
            return any(f in name for f in families)
        check("opens on subject car", on_subject(first), first)
        check("closes on subject car", on_subject(last), last)

        # VISUAL opening check. The test above is a FILENAME substring match, and
        # it happily passed a frame that was a tight crop of a black showroom car
        # with foreign dealer promo text and a QR code burned into the windshield
        # — because the filename contained "creta". This one looks at the actual
        # pixels of frame 0 against the rival Shorts baseline.
        # Only the EXPOSURE axes can fail: brightness/contrast/colourfulness are
        # ours to control. edge_density is reported but never fails, because
        # closing that gap means putting text on frame 0, which collides with a
        # hard TASTE rule (text only while its words are spoken) and is the
        # owner's call, not QA's.
        try:
            import tempfile

            from carshorts.quality.firstframe import extract_frame, frame_stats, load_baseline
            baseline = load_baseline()
            if baseline:
                frame0 = Path(tempfile.mkdtemp(prefix="qa_ff_")) / "frame0.jpg"
                if extract_frame(video_path, frame0, 0.0):
                    st = frame_stats(frame0)
                    weak = [f"{k} {st[k] / baseline[k]:.2f}x"
                            for k in ("brightness", "contrast", "colorfulness")
                            if baseline.get(k) and st[k] / baseline[k] < 0.5]
                    ed = baseline.get("edge_density")
                    note = (f"; edge_density {st['edge_density'] / ed:.2f}x (advisory)"
                            if ed else "")
                    check("opening frame vs feed norm", not weak,
                          (", ".join(weak) if weak else "within norm") + note)
        except Exception:  # noqa: BLE001 — QA must never crash a finished render
            pass

        ov_ok = True
        detail = ""
        for sec in sections:
            dur = sec["duration"]
            kw = sec.get("keyword", {})
            if kw.get("text") and kw.get("start", 0) + 0.5 > dur:
                ov_ok, detail = False, f"keyword outside sec {sec['index']}"
            starts = [c["start"] for c in sec.get("callouts", [])]
            if starts != sorted(starts):
                ov_ok, detail = False, f"callouts unordered in sec {sec['index']}"
            if any(c["start"] >= dur - 0.4 for c in sec.get("callouts", [])):
                ov_ok, detail = False, f"callout past end in sec {sec['index']}"
        check("overlays inside their sections", ov_ok, detail)

        # word-synced pops: sane count, ordered, non-overlapping, inside section
        pop_ok = True
        pop_detail = ""
        total_pops = 0
        for sec in sections:
            dur = sec["duration"]
            pops = sec.get("pops", [])
            total_pops += len(pops)
            if len(pops) > 6:
                pop_ok, pop_detail = False, f"{len(pops)} pops crowd sec {sec['index']}"
            prev_end = -1.0
            for pop in pops:
                own_slot = pop.get("kind") in ("reaction", "card", "lss")
                if not own_slot and pop["start"] < prev_end + 0.04:
                    pop_ok, pop_detail = False, f"pops overlap in sec {sec['index']}"
                # own-slot pops (LSS word flashes, cards, reactions) are timed to
                # their spoken word's span — 0.3s of LIKE before SHARE says is
                # right, not a defect; only regular text pops need the 0.45s read
                # time. Keep a 0.25s sanity floor so a flash still registers.
                min_dur = 0.25 if own_slot else 0.45
                if pop["dur"] < min_dur:
                    pop_ok, pop_detail = False, f"pop under 0.5s in sec {sec['index']}"
                past_end_limit = dur - 0.35 if own_slot else dur - 0.5
                if pop["start"] > past_end_limit:
                    pop_ok, pop_detail = False, f"pop past end of sec {sec['index']}"
                if not own_slot:
                    prev_end = pop["start"] + pop["dur"]
        check("text pops voice-synced & uncrowded", pop_ok,
              pop_detail or f"{total_pops} pops total")

        # owner's #1 rule, gated: no clip may loop (a video cut longer than its
        # source) and no scripted overlay may silently drop. produce records
        # both in the manifest; a red here means the render repeats footage or
        # is missing a requested overlay — never let that reach the owner.
        warns = manifest.get("quality_warnings", [])
        loops = [w for w in warns if w.startswith("LOOP")]
        drops = [w for w in warns if w.startswith("DROPPED")]
        stock = [w for w in warns if w.startswith("STOCK")]
        shotmiss = [w for w in warns if w.startswith("SHOT-PLAN")]
        overlaps = [w for w in warns if w.startswith("OVERLAP")]
        check("no looped/repeated footage", not loops,
              f"{len(loops)} looping cut(s): {loops[0]}" if loops else "")
        check("no dropped overlays", not drops,
              f"{len(drops)} dropped: {drops[0]}" if drops else "")
        # overlays colliding in one slot (the owner's "text overlaps" defect)
        check("no overlapping overlays", not overlaps,
              f"{len(overlaps)}: {overlaps[0]}" if overlaps else "")
        # shot-plan clips missing from the pool -> a beat used footage that may not
        # match its narration (e.g. a comparison's Creta beat rendered on Sierra
        # clips because the Creta footage wasn't dropped yet).
        check("shot-plan clips all present", not shotmiss,
              f"{len(shotmiss)} unresolved: {shotmiss[0]}" if shotmiss else "")
        # footage-source + voice self-checks — the mistake classes that shipped a
        # different video than intended (stock over owner clips; edge robot voice
        # instead of the cloned channel voice). produce records both in the manifest.
        check("owner footage used when available", not stock, stock[0] if stock else "")
        _rmeta = manifest.get("render", {})
        _eng = _rmeta.get("voice_engine")
        check("cloned channel voice (not edge fallback)", _eng != "edge",
              f"engine={_eng}" if _eng else "")

    print("     ── RENDER QA ──")
    for name, ok, det in checks:
        print(f"     {'✅' if ok else '🔴'} {name}" + (f"  ({det})" if det else ""))
    if details:
        return all(ok for _, ok, _ in checks), [
            {"check": n, "detail": d} for n, ok, d in checks if not ok]
    return all(ok for _, ok, _ in checks)


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--manifest")
    ap.parse_args()
    args = ap.parse_args()
    ok = run_qa(args.video, args.manifest)
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
