"""Visual QA — the system finally SEES its own output.

  python -m carshorts.quality.vqa out/thar_final.mp4        # uses <name>.manifest.json

For every cut in the manifest, samples the rendered frame at that cut's
midpoint and sends ALL frames in ONE Gemini vision call (fits the free tier),
asking per frame:
  - does the visual plausibly match the narration phrase playing over it?
  - defects: readable number plate, third-party watermark/logo, wrong vehicle
    type, too dark/blurry, clutter.

Prints a per-cut verdict board; failures are appended to data/failures.jsonl.
Vision is advisory (LLM judgment) — deterministic QA stays the hard gate.
"""
from __future__ import annotations

import datetime
import json
import subprocess
import tempfile
from pathlib import Path

from carshorts.core import paths

# Vision issues split by severity — and, within blocking, by how trustworthy a
# SINGLE-frame flag is:
#   HARD_BLOCKING — objective, hard-rule breaches (a legible plate, someone else's
#     logo). One frame is enough: the owner rule is plates blurred/excluded and
#     never watermarked/ripped content, so these are never softened.
#   CORROBORATED_BLOCKING — real but false-positive-prone. wrong_vehicle_type fires
#     on a car glimpsed in ONE sampled frame — a vehicle passing in the background,
#     a reflection, an aircraft through a sunroof — which must NOT quarantine a clip
#     that is otherwise on-subject. It blocks only when >= CORROBORATION_MIN frames
#     OF THE SAME CLIP agree (a genuinely wrong clip shows the wrong car throughout).
# Everything else (clutter, dark/blur, a lone mismatch) stays advisory.
HARD_BLOCKING = {"readable_plate", "watermark_or_logo_overlay"}
CORROBORATED_BLOCKING = {"wrong_vehicle_type"}
BLOCKING_ISSUES = HARD_BLOCKING | CORROBORATED_BLOCKING  # kept for callers/tests
CORROBORATION_MIN = 2   # frames of one clip that must agree before wrong_vehicle blocks


def blocking_fails(fails: list[dict], corroboration_min: int = CORROBORATION_MIN) -> list[dict]:
    """Filter flagged frames down to the BLOCKING ones, tiered: any HARD issue
    blocks its frame outright; a CORROBORATED issue (wrong_vehicle_type) blocks
    only if that clip has >= corroboration_min frames carrying it. Pure — the
    quarantine/gate decisions all flow from this, so it is unit-tested directly."""
    corro_counts: dict[str, int] = {}
    for f in fails:
        if set(f.get("issues", [])) & CORROBORATED_BLOCKING:
            asset = f.get("asset", "")
            corro_counts[asset] = corro_counts.get(asset, 0) + 1
    out = []
    for f in fails:
        issues = set(f.get("issues", []))
        hard = bool(issues & HARD_BLOCKING)
        corroborated = bool(issues & CORROBORATED_BLOCKING) and \
            corro_counts.get(f.get("asset", ""), 0) >= corroboration_min
        if hard or corroborated:
            out.append(f)
    return out


def _extract_frame(video: str, t: float, out_path: str) -> bool:
    proc = subprocess.run(
        ["ffmpeg", "-y", "-ss", f"{t:.2f}", "-i", video,
         "-frames:v", "1", "-vf", "scale=360:-1", out_path],
        capture_output=True)
    return proc.returncode == 0 and Path(out_path).exists()


def run_vqa(video_path: str, manifest_path: str | None = None,
            max_frames: int = 18) -> bool:
    manifest_path = manifest_path or str(Path(video_path).with_suffix(".manifest.json"))
    manifest = json.loads(Path(manifest_path).read_text())

    # global timeline of cuts: (abs_time_mid, phrase_text_near, asset)
    samples = []
    offset = 0.0
    for sec in manifest.get("sections", []):
        cuts = sec.get("cuts", [])
        phrases = sec.get("phrases", [])
        for ci, cut in enumerate(cuts):
            start = cut["t"]
            end = cuts[ci + 1]["t"] if ci + 1 < len(cuts) else sec["duration"]
            mid = offset + (start + end) / 2
            phrase = ""
            for ph in phrases:      # phrase playing at this cut
                if ph["t"] <= (start + end) / 2:
                    phrase = ph["text"]
            samples.append({"t": round(mid, 2), "phrase": phrase,
                            "asset": cut.get("asset", "")})
        offset += sec["duration"]
    samples = samples[:max_frames]

    tdir = Path(tempfile.mkdtemp(prefix="vqa_"))
    frames = []
    for i, sm in enumerate(samples):
        fp = str(tdir / f"f{i:02d}.jpg")
        if _extract_frame(video_path, sm["t"], fp):
            frames.append((sm, fp))
    if not frames:
        print("     VQA: no frames extracted")
        return True

    from PIL import Image

    from carshorts.adapters.llm import gemini_vision
    parts = ["You are the visual QA for a car YouTube Short. For EACH numbered "
             "frame below, given the narration phrase playing over it, judge:\n"
             "- match: does the visual plausibly fit the phrase (a generic but "
             "non-contradicting visual counts as true)?\n"
             "- issues: any of [readable_plate, watermark_or_logo_overlay, "
             "wrong_vehicle_type, too_dark_or_blurry, clutter]. Empty if clean.\n"
             'Output ONLY a JSON array: [{"frame": 0, "match": true, "issues": []}]\n']
    for i, (sm, fp) in enumerate(frames):
        parts.append(f'Frame {i}: narration = "{sm["phrase"]}" (asset {sm["asset"]})')
        parts.append(Image.open(fp))

    verdicts = json.loads(gemini_vision(parts))

    fails = []
    print("     ── VISUAL QA ──")
    for v in verdicts:
        idx = v.get("frame", -1)
        if not (0 <= idx < len(frames)):
            continue
        sm = frames[idx][0]
        bad = (not v.get("match", True)) or v.get("issues")
        mark = "🔴" if bad else "✅"
        note = ",".join(v.get("issues", [])) or ("mismatch" if not v.get("match", True) else "")
        print(f"     {mark} t={sm['t']:5.1f}s {Path(sm['asset']).stem[:28]:30} {note}")
        if bad:
            fails.append({"t": sm["t"], "asset": sm["asset"], "phrase": sm["phrase"],
                          "issues": v.get("issues", []), "match": v.get("match", True)})

    blocking = blocking_fails(fails)
    # A machine-readable verdict beside the video so callers (the pipeline) can
    # gate on it without re-parsing stdout.
    Path(video_path).with_suffix(".vqa.json").write_text(json.dumps({
        "video": video_path, "frames": len(frames), "flagged": len(fails),
        "blocking": len(blocking),
        "blocking_detail": [{"t": f["t"], "asset": f["asset"], "issues": f["issues"]}
                            for f in blocking],
    }, indent=2))

    if fails:
        journal = paths.FAILURES
        journal.parent.mkdir(parents=True, exist_ok=True)
        with journal.open("a") as fh:
            for f in fails:
                fh.write(json.dumps({
                    "at": datetime.datetime.now().isoformat(timespec="seconds"),
                    "video": video_path, "check": "visual-qa",
                    "detail": json.dumps(f, ensure_ascii=False), "resolved": False}) + "\n")
        tag = (f", {len(blocking)} with BLOCKING issues (plates/wrong-vehicle/watermark)"
               if blocking else " (advisory)")
        print(f"     VQA: {len(fails)}/{len(frames)} frames flagged{tag}")
    else:
        print(f"     VQA: all {len(frames)} frames clean")
    return not fails


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--manifest")
    args = ap.parse_args()
    ok = run_vqa(args.video, args.manifest)
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
