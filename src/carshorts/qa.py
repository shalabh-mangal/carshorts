"""Render QA gate — every finished video is validated layer by layer.

  python -m carshorts.qa out/thar_draft.mp4            # uses <name>.manifest.json

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

    check("runtime ≤ 63s (Shorts sweet spot)", actual <= 63.0, f"{actual:.1f}s")

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
        check("opens on subject car", _family(first) in CAR_FAMILIES, first)
        check("closes on subject car", _family(last) in CAR_FAMILIES, last)

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
            if len(pops) > 2:
                pop_ok, pop_detail = False, f"{len(pops)} pops crowd sec {sec['index']}"
            prev_end = -1.0
            for pop in pops:
                if pop["start"] < prev_end + 0.4:
                    pop_ok, pop_detail = False, f"pops overlap in sec {sec['index']}"
                if pop["start"] + 0.5 > dur:
                    pop_ok, pop_detail = False, f"pop past end of sec {sec['index']}"
                prev_end = pop["start"] + pop["dur"]
        check("text pops voice-synced & uncrowded", pop_ok,
              pop_detail or f"{total_pops} pops total")

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
