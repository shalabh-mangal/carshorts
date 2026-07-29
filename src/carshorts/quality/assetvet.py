"""Asset vet — look at fetched images BEFORE they can reach a render.

  python -m carshorts.quality.assetvet assets/cars/maruti-suzuki-brezza/images \
      --subject "Maruti Suzuki Brezza"                # report only
  python -m carshorts.quality.assetvet <dir> --subject "..." --apply   # + quarantine

CLAUDE.md has always said "new stock/CC fetches get a visual vet grid before
entering the pool" — but nothing implemented it. vqa.py could already SEE these
exact defects (readable_plate, watermark, wrong_vehicle), except it only looked
AFTER a 12-minute render, by which point a plated frame is already in the video.

This moves the eyes forward to fetch time. Confirmed necessary on 2026-07-23:
an auto-fetch of "Mahindra Thar" returned three Wikimedia stills — all three had
readable number plates, and one was a previous-generation car carrying a
third-party watermark. WikimediaImageSource checks the LICENCE, nothing else.

Defects are QUARANTINED (moved to <dir>/_quarantine/), never deleted — a vision
model is advisory, and the owner must be able to overrule it by moving a file
back. Deterministic QA stays the hard gate.
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

QUARANTINE = "_quarantine"
REPORT = "vet_report.json"

_PROMPT = (
    "You are the asset vet for a car YouTube channel. For EACH numbered image "
    "judge it as stock footage for a video about the SUBJECT NAMEPLATE.\n"
    "Report these defects (empty list if clean):\n"
    "  readable_plate        - a number plate whose characters can be READ. "
    "A blurred, masked or illegible plate is NOT this defect.\n"
    "  watermark             - a third-party watermark, logo overlay or site "
    "branding burned into the image. Manufacturer badging on the car itself "
    "is NOT a watermark.\n"
    "  wrong_vehicle         - a DIFFERENT NAMEPLATE entirely (another model "
    "or another brand). Use this ONLY when the car is not the subject "
    "nameplate at all.\n"
    "  wrong_generation      - the CORRECT nameplate but an older or different "
    "generation/facelift than the target generation.\n"
    "  too_dark_or_blurry    - genuinely unusable image quality.\n"
    "\nCRITICAL DISAMBIGUATION: if the car IS the subject nameplate but looks "
    "like an earlier generation, that is `wrong_generation`, NEVER "
    "`wrong_vehicle`. Older generations are often used deliberately. "
    "`wrong_vehicle` is reserved for a genuinely different model/brand.\n"
    "Be strict about plates and watermarks — those are hard disqualifiers.\n"
    "When (and ONLY when) you report readable_plate, ALSO give \"plate_box\": "
    "[x0,y0,x1,y1] as fractions of image width/height (0.0-1.0) tightly around "
    "the number plate, so it can be blurred and the shot saved.\n"
    'Output ONLY a JSON array: '
    '[{"image": 0, "defects": [], "note": "", "plate_box": null}]'
)

# defects that must never reach a render
BLOCKING = {"readable_plate", "watermark", "wrong_vehicle", "too_dark_or_blurry"}
# advisory: an older generation is sometimes deliberate (an "old news" beat)
ADVISORY = {"wrong_generation"}


def decide(defects: list[str]) -> tuple[bool, list[str]]:
    """(clean_enough_to_use, blocking_reasons). Advisory defects don't block."""
    blocking = [d for d in defects if d in BLOCKING]
    return (not blocking), blocking


def _blur_box(path: str | Path, box: list[float]) -> None:
    """Pixelate a normalized [x0,y0,x1,y1] region (0-1) with 25% padding, hard
    enough that any plate characters become illegible."""
    from PIL import Image, ImageFilter
    im = Image.open(path).convert("RGB")
    width, height = im.size
    x0, y0, x1, y1 = box
    pad_w, pad_h = (x1 - x0) * 0.25, (y1 - y0) * 0.25
    left = max(0, int((x0 - pad_w) * width)); top = max(0, int((y0 - pad_h) * height))
    right = min(width, int((x1 + pad_w) * width)); bot = min(height, int((y1 + pad_h) * height))
    if right - left < 4 or bot - top < 4:
        return
    region = im.crop((left, top, right, bot))
    small = region.resize((max(1, region.width // 20), max(1, region.height // 8)))
    im.paste(small.resize(region.size, Image.NEAREST).filter(ImageFilter.GaussianBlur(10)),
             (left, top, right, bot))
    im.save(path)


def _recover_plate(path: Path, subject: str, box: list[float], vet_fn,
                   generation: str = "") -> bool:
    """Blur the detected plate, then CONFIRM with one re-vet that it is now
    unreadable. Returns True only if the shot is genuinely clean afterwards —
    a still-readable plate is never kept (the owner rule: plates blurred OR
    excluded). Any error means 'do not keep' (caller quarantines)."""
    try:
        _blur_box(path, box)
        verdict = (parse_verdicts(vet_fn([path], subject, generation)) or [{}])[0]
        return "readable_plate" not in (verdict.get("defects") or [])
    except Exception:  # noqa: BLE001
        return False


def parse_verdicts(raw: str) -> list[dict]:
    """Tolerant parse of the model's JSON array."""
    import re
    cleaned = re.sub(r"```(?:json)?", "", raw or "").strip()
    start, end = cleaned.find("["), cleaned.rfind("]")
    if start == -1 or end <= start:
        return []
    try:
        rows = json.loads(cleaned[start:end + 1])
    except json.JSONDecodeError:
        return []
    out = []
    for row in rows if isinstance(rows, list) else []:
        if isinstance(row, dict) and "image" in row:
            box = row.get("plate_box")
            if isinstance(box, (list, tuple)) and len(box) == 4:
                try:
                    box = [float(v) for v in box]
                    if any(v > 1.0 for v in box):   # 0-1000 convention -> 0-1
                        box = [v / 1000.0 for v in box]
                except (TypeError, ValueError):
                    box = None
            else:
                box = None
            out.append({"image": row.get("image"),
                        "defects": [str(d) for d in (row.get("defects") or [])],
                        "note": str(row.get("note", "")), "plate_box": box})
    return out


def _gemini_vet(paths: list[Path], subject: str, generation: str = "") -> str:
    """One vision call for the whole batch (free-tier friendly).

    NOTE: google.generativeai is end-of-life upstream (migrate to google.genai).
    """
    import os

    import google.generativeai as genai
    from PIL import Image

    genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
    model = genai.GenerativeModel("gemini-2.5-flash")
    target = (f"SUBJECT NAMEPLATE: {subject}\n"
              + (f"TARGET GENERATION: {generation}\n" if generation else
                 "TARGET GENERATION: any generation is acceptable\n"))
    parts = [f"{_PROMPT}\n\n{target}"]
    for i, p in enumerate(paths):
        parts.append(f"Image {i}: filename {p.name}")
        # copy into memory so the file HANDLE closes immediately — otherwise on
        # Windows a later shutil.move of a quarantined/recovered image throws
        # WinError 32 ("file in use by another process").
        with Image.open(p) as _im:
            parts.append(_im.convert("RGB").copy())
    resp = model.generate_content(
        parts, generation_config={"response_mime_type": "application/json"})
    return resp.text


def vet_folder(folder: str | Path, subject: str, apply: bool = False,
               batch: int = 14, vet_fn=None, generation: str = "") -> dict:
    """Vet every image in `folder`. Returns a report; optionally quarantines.

    vet_fn is injectable so the decision/quarantine logic is testable without
    a network call or an API key.
    """
    folder = Path(folder)
    images = sorted(p for p in folder.glob("*")
                    if p.suffix.lower() in (".jpg", ".jpeg", ".png")
                    and p.parent.name != QUARANTINE)
    if not images:
        return {"checked": 0, "clean": 0, "quarantined": 0, "results": []}

    vet_fn = vet_fn or _gemini_vet
    import time as _time
    results: list[dict] = []
    errors: list[str] = []
    n_batches = (len(images) + batch - 1) // batch
    quota_dead = False
    for bi, start in enumerate(range(0, len(images), batch)):
        chunk = images[start:start + batch]
        # Once the daily quota is exhausted every further call just 429s. Stop
        # calling and mark the rest unvetted rather than hammering a dead quota
        # (the first Creta run fired 32 doomed calls after quota died).
        if quota_dead:
            for path in chunk:
                results.append({"file": path.name, "ok": True, "defects": [],
                                "blocking": [], "note": "unvetted (quota exhausted)",
                                "vetted": False})
            continue
        try:
            raw = vet_fn(chunk, subject, generation)
            verdicts = {v["image"]: v for v in parse_verdicts(raw)}
        except Exception as exc:  # noqa: BLE001
            # ONE failed batch must not sink the folder or discard the batches
            # that already succeeded. Mark this chunk UNVETTED — never
            # quarantined on no evidence — and keep going.
            msg = str(exc)
            errors.append(msg[:120])
            # Distinguish a DAILY QUOTA cap (permanent for the run — stop) from a
            # transient per-minute rate limit (a plain 429 — keep going, the
            # pacing between batches is exactly the remedy for that).
            if "quota" in msg.lower():
                quota_dead = True
            print(f"  batch {bi + 1}/{n_batches} failed ({msg[:90]}) — "
                  f"marking {len(chunk)} image(s) unvetted"
                  + (", quota exhausted, stopping calls" if quota_dead else ", continuing"))
            for path in chunk:
                results.append({"file": path.name, "ok": True, "defects": [],
                                "blocking": [], "note": "unvetted (batch error)",
                                "vetted": False})
            continue
        for i, path in enumerate(chunk):
            v = verdicts.get(i, {"defects": [], "note": "no verdict"})
            ok, blocking = decide(v["defects"])
            results.append({"file": path.name, "ok": ok, "defects": v["defects"],
                            "blocking": blocking, "note": v.get("note", ""),
                            "plate_box": v.get("plate_box"), "vetted": True})
        if bi + 1 < n_batches:
            _time.sleep(2.0)   # pace calls under the free-tier per-minute limit

    quarantined = 0
    recovered = 0
    if apply:
        qdir = folder / QUARANTINE
        for r in results:
            # only quarantine on an ACTUAL verdict, never on an unvetted image
            if not (r.get("vetted") and not r["ok"]):
                continue
            src = folder / r["file"]
            if not src.exists():
                continue
            # RECOVER a plated-but-otherwise-good shot by blurring the plate
            # (confirmed by re-vet) instead of losing it — the exact case that
            # cost us the two good Tata Punch beauty shots.
            if r["blocking"] == ["readable_plate"] and r.get("plate_box") and \
                    _recover_plate(src, subject, r["plate_box"], vet_fn, generation):
                r["ok"] = True
                r["blocking"] = []
                r["note"] = (r.get("note", "") + " [plate blurred, recovered]").strip()
                recovered += 1
                continue
            qdir.mkdir(exist_ok=True)
            shutil.move(str(src), str(qdir / r["file"]))
            quarantined += 1

    vetted = [r for r in results if r.get("vetted")]
    report = {"subject": subject, "checked": len(results),
              "vetted": len(vetted), "unvetted": len(results) - len(vetted),
              "clean": sum(1 for r in vetted if r["ok"]),
              "quarantined": quarantined, "recovered": recovered,
              "errors": errors[:5], "results": results}
    try:
        (folder / REPORT).write_text(json.dumps(report, indent=2, ensure_ascii=False),
                                     encoding="utf-8")
    except OSError:
        pass
    return report


# --------------------------------------------------------------------------
# Persistent cache + vet-on-use.
# Bulk-vetting a whole pool is quota-hostile: ~350 curated images in a day
# exceeds the Gemini free tier. But a render only ever SHOWS a handful. So vet
# lazily — only the images a render actually considers — and cache each verdict
# FOREVER, so no image is ever vetted twice. Over a few renders every
# commonly-used image gets vetted, and free quota is never exceeded.
# --------------------------------------------------------------------------
CACHE = Path("data/vet_cache.json")


def _file_key(path: str | Path) -> str:
    """Stable per-file key: parent/name:size. A re-saved image (different bytes)
    changes size and is correctly re-vetted."""
    p = Path(path)
    try:
        size = p.stat().st_size
    except OSError:
        size = 0
    return f"{p.parent.name}/{p.name}:{size}"


def load_cache(cache_path: Path = CACHE) -> dict:
    if cache_path.exists():
        try:
            return json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass
    return {}


def save_cache(cache: dict, cache_path: Path = CACHE) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")


def seed_cache_from_reports(root: str | Path = "assets/cars",
                            cache_path: Path = CACHE) -> int:
    """Ingest every existing vet_report.json into the cache — so all vetting
    already paid for (report-only runs included) is preserved, not repeated."""
    cache = load_cache(cache_path)
    added = 0
    for report in Path(root).rglob(REPORT):
        try:
            data = json.loads(report.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        for r in data.get("results", []):
            # pre-resilience reports had no "vetted" field; every row in them is
            # a genuine verdict, so a missing field means vetted.
            if not r.get("vetted", True):
                continue
            key = _file_key(report.parent / r["file"])
            if key not in cache:
                cache[key] = {"ok": r["ok"], "defects": r.get("defects", []),
                              "blocking": r.get("blocking", [])}
                added += 1
    save_cache(cache, cache_path)
    return added


def vet_paths(paths: list[str | Path], subject: str, generation: str = "",
              max_calls: int = 8, batch: int = 6, cache_path: Path = CACHE,
              vet_fn=None) -> dict:
    """Vet-on-use: return {str(path): verdict} for each path, cache-first.

    Cached files cost nothing. Uncached files are vetted in batches until
    `max_calls` batches are spent or the daily quota dies; anything past that is
    returned `unvetted` (ok=True, vetted=False) — never blocked on no evidence.
    Verdicts are persisted so the next render starts from a warmer cache.
    """
    vet_fn = vet_fn or _gemini_vet
    cache = load_cache(cache_path)
    out: dict[str, dict] = {}
    todo: list[Path] = []
    for p in paths:
        key = _file_key(p)
        hit = cache.get(key)
        if hit is not None:
            out[str(p)] = {**hit, "vetted": True, "cached": True}
        else:
            todo.append(Path(p))

    calls = 0
    quota_dead = False
    for start in range(0, len(todo), batch):
        chunk = todo[start:start + batch]
        if quota_dead or calls >= max_calls:
            for p in chunk:
                out[str(p)] = {"ok": True, "defects": [], "blocking": [],
                               "vetted": False}
            continue
        calls += 1
        try:
            verdicts = {v["image"]: v for v in parse_verdicts(vet_fn(chunk, subject, generation))}
        except Exception as exc:  # noqa: BLE001
            if "quota" in str(exc).lower():
                quota_dead = True
            for p in chunk:
                out[str(p)] = {"ok": True, "defects": [], "blocking": [],
                               "vetted": False}
            continue
        for i, p in enumerate(chunk):
            v = verdicts.get(i, {"defects": []})
            ok, blocking = decide(v.get("defects", []))
            rec = {"ok": ok, "defects": v.get("defects", []), "blocking": blocking}
            cache[_file_key(p)] = rec
            out[str(p)] = {**rec, "vetted": True, "cached": False}

    save_cache(cache, cache_path)
    return out


def quarantine_from_report(folder: str | Path) -> list[str]:
    """Move the blocking failures recorded in a folder's saved vet_report.json
    into _quarantine/ — WITHOUT re-running vision. Lets a report-only pass be
    applied later at zero quota cost. Returns the filenames moved."""
    folder = Path(folder)
    report = folder / REPORT
    if not report.exists():
        return []
    data = json.loads(report.read_text(encoding="utf-8"))
    moved = []
    qdir = folder / QUARANTINE
    for r in data.get("results", []):
        # missing "vetted" (pre-resilience report) means it IS a real verdict
        if r.get("vetted", True) and not r["ok"]:
            src = folder / r["file"]
            if src.exists():
                qdir.mkdir(exist_ok=True)
                shutil.move(str(src), str(qdir / r["file"]))
                moved.append(r["file"])
    return moved


def main() -> None:
    ap = argparse.ArgumentParser(description="Vet fetched car images before they reach a render.")
    ap.add_argument("folder", help="Image folder, e.g. assets/cars/<slug>/images")
    ap.add_argument("--subject", required=True,
                    help='Subject NAMEPLATE only, e.g. "Mahindra Thar" (not the generation).')
    ap.add_argument("--generation", default="",
                    help='Optional target generation, e.g. "2026 ROXX facelift". '
                         'Mismatches are advisory (wrong_generation), never blocking.')
    ap.add_argument("--apply", action="store_true",
                    help="Move failures into _quarantine/ (default: report only).")
    ap.add_argument("--apply-report", action="store_true",
                    help="Quarantine the failures in the SAVED vet_report.json "
                         "without re-running vision (zero quota).")
    args = ap.parse_args()

    if args.apply_report:
        moved = quarantine_from_report(args.folder)
        print(f"quarantined {len(moved)} file(s) from the saved report:")
        for m in moved:
            print(f"   ✂ {m}")
        return

    print(f"asset vet — {args.folder}  (subject: {args.subject}"
          + (f", target gen: {args.generation}" if args.generation else "") + ")")
    report = vet_folder(args.folder, args.subject, apply=args.apply,
                        generation=args.generation)
    if not report["checked"]:
        print("  nothing checked")
        return
    for r in report["results"]:
        mark = "OK  " if r["ok"] else "FAIL"
        detail = ",".join(r["defects"]) or "clean"
        print(f"  {mark} {r['file'][:52]:<54} {detail}")
    print(f"\n  {report['clean']}/{report['checked']} clean"
          + (f", {report['quarantined']} quarantined -> {QUARANTINE}/"
             if args.apply else "  (report only; --apply to quarantine)"))


if __name__ == "__main__":
    main()
