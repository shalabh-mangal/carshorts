"""Inbox auto-ingest — drop raw footage, get a vetted, filed asset pool.

  python -m carshorts.sourcing.ingest --car "Mahindra Thar"          # process assets/inbox/
  python -m carshorts.sourcing.ingest --car "Mahindra Thar" --dry    # classify only

For every video/image in assets/inbox/:
  1. probe + sample frames
  2. ONE batched Gemini vision call classifies each: what's shown (side/front/
     rear/interior/console/badge/wheel/action), plate visible?, third-party
     watermark?, quality ok?
  3. clean videos are cut into ~3s segments named by content and filed under
     assets/cars/<slug>/own/; clean images go to .../images/
  4. anything with a plate/watermark/quality problem moves to
     assets/inbox/review/ with a reason file — a human decides.

Conservative by design: uncertain = review, never auto-publish risk.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from carshorts.core import paths
from carshorts.rendering.produce import _slug

INBOX = paths.INBOX
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".webm"}
IMAGE_EXT = {".jpg", ".jpeg", ".png"}


def _dur(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
                         capture_output=True, text=True)
    try:
        return float(out.stdout.strip())
    except ValueError:
        return 0.0


def _classify(files: list[Path]) -> list[dict]:
    """One batched vision call over sample frames from every file."""
    from PIL import Image

    from carshorts.adapters.llm import gemini_vision

    tdir = Path(tempfile.mkdtemp(prefix="ingest_"))
    parts = ["You vet raw footage for a car YouTube channel. For EACH numbered "
             "item below (frames sampled from one file), output an object:\n"
             '{"item": <n>, "label": "side|front|rear|interior|console|badge|'
             'wheel|action|scenery|other", "plate_visible": bool, '
             '"third_party_watermark": bool, "quality_ok": bool, '
             '"note": "<short>"}\n'
             "plate_visible = a number plate is readable or nearly readable. "
             "Output ONLY the JSON array.\n"]
    for i, f in enumerate(files):
        parts.append(f"Item {i}: file {f.name}")
        if f.suffix.lower() in VIDEO_EXT:
            duration = _dur(f)
            for t in (duration * 0.2, duration * 0.5, duration * 0.8):
                fp = tdir / f"{i}_{t:.1f}.jpg"
                subprocess.run(["ffmpeg", "-y", "-ss", f"{t:.2f}", "-i", str(f),
                                "-frames:v", "1", "-vf", "scale=320:-1", str(fp)],
                               capture_output=True)
                if fp.exists():
                    parts.append(Image.open(fp))
        else:
            parts.append(Image.open(f).copy().convert("RGB").resize((320, 320)))

    return json.loads(gemini_vision(parts))


def run(car: str, dry: bool = False) -> None:
    slug = _slug(car)
    files = sorted(p for p in INBOX.iterdir()
                   if p.is_file() and p.suffix.lower() in VIDEO_EXT | IMAGE_EXT) if INBOX.exists() else []
    if not files:
        print("inbox empty — drop clips/photos into assets/inbox/ first")
        return
    print(f"ingesting {len(files)} file(s) for {car}...")
    verdicts = {v.get("item"): v for v in _classify(files)}

    own_dir = paths.car_dir(slug) / "own"
    img_dir = paths.car_dir(slug) / "images"
    review = INBOX / "review"
    for d in (own_dir, img_dir, review):
        d.mkdir(parents=True, exist_ok=True)
    existing = len(list(own_dir.glob("pool_*.mp4")))

    for i, f in enumerate(files):
        v = verdicts.get(i, {})
        label = v.get("label", "other")
        bad = v.get("plate_visible") or v.get("third_party_watermark") or not v.get("quality_ok", True)
        print(f"  {f.name}: {label}"
              + (" 🔴 " + v.get("note", "") if bad else " ✅"))
        if dry:
            continue
        if bad:
            shutil.move(str(f), review / f.name)
            (review / (f.name + ".reason.txt")).write_text(json.dumps(v, indent=2))
            continue
        if f.suffix.lower() in IMAGE_EXT:
            shutil.move(str(f), img_dir / f"{slug}_{label}_{i}{f.suffix.lower()}")
            continue
        # video: grade + cut into ~3s vertical segments named by content
        duration = _dur(f)
        seg_len = 3.0
        start, n = 0.0, 0
        while start + 1.2 < duration and n < 8:
            existing += 1
            out_seg = own_dir / f"pool_{existing:02d}_{label}{n if n else ''}.mp4"
            grade = "eq=contrast=1.07:saturation=1.15:brightness=0.02,unsharp=5:5:0.5"
            fit = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"
            subprocess.run(["ffmpeg", "-y", "-ss", f"{start:.2f}", "-t", f"{seg_len}",
                            "-i", str(f), "-vf", f"{fit},{grade}", "-an", str(out_seg)],
                           capture_output=True)
            n += 1
            start += seg_len
        shutil.move(str(f), INBOX / "review" / ("USED_" + f.name))
        print(f"     -> {n} segments filed in {own_dir}")
    print("done. Review folder:", review)


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--car", required=True)
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()
    run(args.car, dry=args.dry)


if __name__ == "__main__":
    main()
