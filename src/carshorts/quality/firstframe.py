"""First-frame engineering — on Shorts, frame 1 IS the thumbnail.

  python -m carshorts.quality.firstframe out/creta_selfrender.mp4      # audit ours
  python -m carshorts.quality.firstframe --benchmark                   # rival baseline
  python -m carshorts.quality.firstframe out/x.mp4 --vision --subject "Hyundai Creta"

A Short lives or dies on the swipe-stop. There is no separate thumbnail to hide
behind — the opening frame is the entire pitch, and it gets roughly one blink.
QA already checks that we OPEN ON THE SUBJECT CAR, but nothing has ever asked
whether that frame is actually arresting.

Deliberately NOT built on my opinion of a good frame. It computes deterministic,
citable image statistics and benchmarks them against REAL rival Shorts
thumbnails fetched from the API, so the target is empirical:

  brightness    mean luma 0-255
  contrast      RMS contrast (std of luma) — flat frames read as fog on a feed
  colorfulness  Hasler & Susstrunk (2003) metric
  saturation    mean HSV S
  edge_density  mean Sobel-ish edge response — a proxy for busy vs clean

A vision pass (--vision) can add a subjective read, but the numbers stand alone
and are what the tests cover. Rival THUMBNAILS are public; their retention and
CTR are not, so this measures how a frame LOOKS, never how it performed.
"""
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import tempfile
import urllib.request
from pathlib import Path

from carshorts.core import paths

REPORTS = paths.REPORTS
BASELINE = paths.FIRSTFRAME_BASELINE
_UA = "carshorts/0.1"


def crop_vertical_content(img):
    """Strip YouTube's Shorts letterbox fill.

    The API returns a Short's thumbnail as 1280x720: the real 9:16 frame sits
    centred, and the sides are filled with a DARKENED, BLURRED copy of it (not
    plain black). Roughly two thirds of the pixels are therefore synthetic, and
    measuring them tanks brightness, inflates contrast and dilutes colour —
    which would make any comparison against our own true 9:16 frame meaningless.

    Vertical or square images are returned untouched, so this is a no-op for our
    own renders.
    """
    w, h = img.size
    if h <= 0 or w / h <= 1.2:
        return img
    content_w = round(h * 9 / 16)
    if content_w <= 0 or content_w >= w:
        return img
    left = (w - content_w) // 2
    return img.crop((left, 0, left + content_w, h))


def frame_stats(image_path: str | Path, strip_letterbox: bool = True) -> dict:
    """Deterministic look-metrics for one image."""
    import numpy as np
    from PIL import Image, ImageFilter

    img = Image.open(image_path).convert("RGB")
    if strip_letterbox:
        img = crop_vertical_content(img)
    arr = np.asarray(img).astype("float32")
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]

    luma = 0.299 * r + 0.587 * g + 0.114 * b
    # Hasler & Susstrunk colourfulness
    rg = r - g
    yb = 0.5 * (r + g) - b
    colorfulness = float(
        (rg.std() ** 2 + yb.std() ** 2) ** 0.5
        + 0.3 * (rg.mean() ** 2 + yb.mean() ** 2) ** 0.5)

    mx, mn = arr.max(axis=2), arr.min(axis=2)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0.0)

    edges = np.asarray(img.convert("L").filter(ImageFilter.FIND_EDGES)).astype("float32")

    return {
        "brightness": round(float(luma.mean()), 2),
        "contrast": round(float(luma.std()), 2),
        "colorfulness": round(colorfulness, 2),
        "saturation": round(float(sat.mean()), 4),
        "edge_density": round(float(edges.mean()), 2),
        "width": img.width, "height": img.height,
    }


def extract_frame(video: str | Path, out_path: str | Path, t: float = 0.0) -> bool:
    proc = subprocess.run(
        ["ffmpeg", "-y", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1",
         str(out_path)], capture_output=True)
    return proc.returncode == 0 and Path(out_path).exists()


def _download(url: str, dest: Path) -> bool:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=20) as resp:
            dest.write_bytes(resp.read())
        return True
    except Exception:  # noqa: BLE001 — one bad thumbnail must not stop the sweep
        return False


def build_baseline(limit: int = 20, max_duration: int = 180) -> dict:
    """Fetch rival SHORTS thumbnails and measure what a winning frame looks like."""
    from carshorts.intel.competitors import _recent_videos, _resolve, load_watchlist
    from carshorts.publishing.ytauth import service

    yt = service("youtube", "v3")
    tmp = Path(tempfile.mkdtemp(prefix="ff_"))
    per_channel, all_stats = [], []

    for ref in load_watchlist():
        ch = _resolve(yt, ref)
        if not ch:
            continue
        vids = [v for v in _recent_videos(yt, ch["uploads"], limit)
                if v["duration_s"] <= max_duration]
        ids = [v["id"] for v in vids][:limit]
        if not ids:
            continue
        stats = []
        for start in range(0, len(ids), 50):
            resp = yt.videos().list(part="snippet",
                                    id=",".join(ids[start:start + 50])).execute()
            for it in resp.get("items", []):
                thumbs = it["snippet"].get("thumbnails", {})
                best = (thumbs.get("maxres") or thumbs.get("standard")
                        or thumbs.get("high") or thumbs.get("medium"))
                if not best:
                    continue
                dest = tmp / f"{it['id']}.jpg"
                if _download(best["url"], dest):
                    try:
                        stats.append(frame_stats(dest))
                    except Exception:  # noqa: BLE001
                        continue
        if stats:
            per_channel.append({"channel": ch["title"], "n": len(stats),
                                **_aggregate(stats)})
            all_stats += stats
            print(f"  {ch['title'][:28]:<30} {len(stats)} thumbnails")

    baseline = {"channels": per_channel, "n": len(all_stats), **_aggregate(all_stats)}
    BASELINE.parent.mkdir(parents=True, exist_ok=True)
    BASELINE.write_text(json.dumps(baseline, indent=2), encoding="utf-8")
    return baseline


KEYS = ("brightness", "contrast", "colorfulness", "saturation", "edge_density")


def _aggregate(stats: list[dict]) -> dict:
    if not stats:
        return {}
    return {k: round(statistics.median([s[k] for s in stats]), 3) for k in KEYS}


def _vision_read(image: Path, subject: str) -> str:
    import os

    import google.generativeai as genai
    from PIL import Image as PILImage

    genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
    model = genai.GenerativeModel("gemini-2.5-flash")
    prompt = (
        "This is the FIRST FRAME of a YouTube Short about "
        f"{subject}. On Shorts the first frame is the thumbnail and gets about "
        "one blink to stop a scrolling viewer.\n"
        "Answer strictly as JSON: "
        '{"subject_prominent": true/false, "stops_scroll": true/false, '
        '"readable_text": true/false, "problems": ["..."], "one_fix": "..."}\n'
        "problems may include: subject_too_small, cluttered_background, "
        "low_contrast, dull_colour, awkward_crop, nothing_happening."
    )
    resp = model.generate_content([prompt, PILImage.open(image)],
                                  generation_config={"response_mime_type": "application/json"})
    return resp.text


def audit(video: str | Path, subject: str = "", vision: bool = False) -> dict:
    tmp = Path(tempfile.mkdtemp(prefix="ff_"))
    frame = tmp / "frame0.jpg"
    if not extract_frame(video, frame, 0.0):
        return {"error": "could not extract frame 0"}
    result = {"video": str(video), "frame_stats": frame_stats(frame)}

    if BASELINE.exists():
        try:
            base = json.loads(BASELINE.read_text(encoding="utf-8"))
            result["baseline"] = {k: base.get(k) for k in KEYS}
            result["baseline_n"] = base.get("n")
        except Exception:  # noqa: BLE001
            pass
    if vision and subject:
        try:
            result["vision"] = _vision_read(frame, subject)
        except Exception as exc:  # noqa: BLE001
            result["vision_error"] = str(exc)[:160]
    result["frame_path"] = str(frame)
    return result


# Reaching the feed's norm is the target. brightness/contrast/colourfulness are
# scored one-sided — a median is not an optimum, so exceeding it earns no extra
# credit but is not punished either. edge_density is scored SYMMETRICALLY
# because both a barren frame and a cluttered one fail to stop a scroll.
_REACH_KEYS = ("brightness", "contrast", "colorfulness")


def score_still(stats: dict, baseline: dict) -> float:
    """0..1 stop-power score for one candidate opening still."""
    parts: list[float] = []
    for k in _REACH_KEYS:
        rival = baseline.get(k)
        if rival:
            parts.append(min((stats.get(k) or 0.0) / rival, 1.0))
    rival = baseline.get("edge_density")
    if rival:
        r = (stats.get("edge_density") or 0.0) / rival
        parts.append(min(r, 1.0 / r) if r > 0 else 0.0)
    return round(sum(parts) / len(parts), 4) if parts else 0.0


def choose_opening_still(candidates, baseline: dict, limit: int = 250) -> dict | None:
    """Pick the opening still DETERMINISTICALLY by measured stop-power.

    The LLM phrase-matcher returns a different hook image on every run, which
    means frame 1 — the thumbnail, the single highest-leverage frame in a Short
    — was being chosen at random. This ranks the subject stills against the
    rival baseline instead. Ties break on path so the result is stable.

    `limit` is a safety valve, not a sample: it must exceed a normal pool or the
    result becomes "best of the first N by filename" rather than best of pool.
    Cost is real but acceptable — measured 29.5s for 137 full-size stills
    (~215ms each), against an ~11 minute render. If pools grow much past this,
    cache stats per file rather than lowering the limit.

    IMPORTANT BLIND SPOT: this scores EXPOSURE and STRUCTURE only. It cannot see
    a number plate, a watermark, dealer promo text or an awkward crop — a black
    showroom car with Thai financing text burned into the windshield once scored
    perfectly acceptably. Run assetvet over the pool so defective images are
    quarantined out before selection ever sees them.
    """
    scored = rank_opening_stills(candidates, baseline, limit)
    if not scored:
        return None
    best_score, best_path, best_stats = scored[0]
    return {"path": best_path, "score": best_score, "stats": best_stats,
            "ranked": [(sc, Path(p).name) for sc, p, _ in scored[:5]]}


def rank_opening_stills(candidates, baseline: dict, limit: int = 250) -> list:
    """[(score, path, stats), ...] sorted best-first. One frame_stats per file.

    Exposed so callers (e.g. vet-on-use) can vet the top candidates from the top
    down without paying to score the pool twice. Ties break on path for
    determinism.
    """
    scored = []
    for path in list(candidates)[:limit]:
        try:
            stats = frame_stats(path)
        except Exception:  # noqa: BLE001 — an unreadable candidate is just skipped
            continue
        scored.append((score_still(stats, baseline), str(path), stats))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return scored


def load_baseline() -> dict:
    base = paths.FIRSTFRAME_BASELINE          # read at call time (not import) so a
    if base.exists():                          # re-rooted/patched path is honoured
        try:
            return json.loads(base.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass
    return {}


def compare(ours: dict, baseline: dict) -> list[str]:
    """Plain-language gaps. Only flags differences big enough to act on."""
    notes = []
    thresholds = {"contrast": 0.75, "colorfulness": 0.75, "edge_density": 0.6}
    for key, ratio_floor in thresholds.items():
        mine, theirs = ours.get(key), baseline.get(key)
        if mine is None or not theirs:
            continue
        ratio = mine / theirs
        if ratio < ratio_floor:
            notes.append(f"{key}: {mine} vs rival median {theirs} ({ratio:.2f}x) — "
                         f"frame is flatter/duller than the feed norm")
        elif ratio > 1 / ratio_floor:
            notes.append(f"{key}: {mine} vs rival median {theirs} ({ratio:.2f}x) — "
                         f"markedly busier than the feed norm")
    return notes


def main() -> None:
    ap = argparse.ArgumentParser(description="Audit the opening frame of a Short.")
    ap.add_argument("video", nargs="?", help="Rendered MP4 to audit.")
    ap.add_argument("--benchmark", action="store_true",
                    help="(Re)build the rival thumbnail baseline.")
    ap.add_argument("--subject", default="", help="Subject car (for --vision).")
    ap.add_argument("--vision", action="store_true", help="Add a vision read.")
    ap.add_argument("--limit", type=int, default=20)
    args = ap.parse_args()

    if args.benchmark:
        print("building rival first-frame baseline (Shorts thumbnails)")
        base = build_baseline(limit=args.limit)
        print(f"\nbaseline from {base['n']} thumbnails:")
        for k in KEYS:
            print(f"  {k:<14} {base.get(k)}")
        print(f"\n-> {BASELINE}")
        if not args.video:
            return

    if not args.video:
        raise SystemExit("give a video to audit, or --benchmark")

    res = audit(args.video, subject=args.subject, vision=args.vision)
    if "error" in res:
        raise SystemExit(res["error"])
    print(f"first-frame audit — {args.video}")
    s, base = res["frame_stats"], res.get("baseline")
    for k in KEYS:
        line = f"  {k:<14} {s[k]}"
        if base and base.get(k) is not None:
            line += f"   (rival median {base[k]})"
        print(line)
    if base:
        notes = compare(s, base)
        print("\n  " + ("\n  ".join(notes) if notes
                        else "within the rival norm on every measured axis"))
    if res.get("vision"):
        print(f"\n  vision: {res['vision'][:400]}")
    print(f"\n  frame saved: {res['frame_path']}")


if __name__ == "__main__":
    main()
