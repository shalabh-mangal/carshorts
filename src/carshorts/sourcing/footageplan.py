"""Footage cockpit — what a car's pool HAS, where it came from, and what's missing.

Step 4 of the autonomy roadmap. Until now the loop could only say "needs footage"
(a REPEAT red = too few distinct clips for the cuts). It couldn't say WHICH angles
are thin or HOW MANY more clips are needed — so the owner had to open the folder and
count by hand. And nothing tracked WHERE a clip came from, so ripped ad footage
(the Tata Sierra pool: readable plates + a burned-in "creative representation only"
disclaimer) sat in the pool with no licensing paper trail.

This module answers three questions for a slug, deterministically (no LLM):
  1. COVERAGE  — how many clean, distinct VIDEO clips vs how many cuts a Short needs
                 (the strict rule is one clip per cut — see qa.py "no clip reused
                 across cuts"), plus a per-angle histogram and which ESSENTIAL angles
                 (front/side/rear/interior/action) are missing.
  2. PROVENANCE — which clips have a recorded source+licence (attributions.json for
                 CC stills, footage_sources.json for ingested video) and which are
                 UNVERIFIED — a licensing question the owner must clear before ship.
  3. SHOPPING LIST — the human-readable gap: "need N more distinct clips; missing
                 rear + interior; M clip(s) have no cleared source."

The core (`plan_from_names`) is pure so it's unit-tested without a filesystem; the
`assess` wrapper reads the actual pool. Wired into the autoloop's `surface` outcome
so a footage-blocked render tells the owner exactly what to shoot/source next.
"""
from __future__ import annotations

import json
from pathlib import Path

from carshorts.core import paths

VIDEO_EXT = {".mp4", ".mov", ".m4v", ".webm"}
IMAGE_EXT = {".jpg", ".jpeg", ".png"}

# A publish-quality Short runs ~8-14 phrase-synced cuts; the strict no-repeat rule
# wants one distinct clip per cut. Stills legitimately fill gaps, so this is the
# VIDEO target — the number below which the REPEAT gate starts going red.
DEFAULT_TARGET_CUTS = 10

# Angle keywords -> canonical angle. Forgiving: matches our ingest naming
# (pool_NN_<label>) AND owner free-naming (sierra_hero, sierra_dash, sierra_sand).
# First keyword found in the filename wins; longest/most-specific listed first.
_ANGLE_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("interior", ("interior", "cabin", "dash", "console", "seat", "sunroof",
                  "screen", "touchscreen", "steering", "cockpit")),
    ("front",    ("front", "hero", "face", "grille", "nose", "headlight", "drl")),
    ("rear",     ("rear", "back", "tail", "boot")),
    ("side",     ("side", "profile", "flank", "door", "alloy", "wheel", "tyre", "tire")),
    ("action",   ("action", "drive", "driving", "road", "sand", "dune", "sea",
                  "lake", "grass", "offroad", "off_road", "pov", "highway", "track")),
    ("badge",    ("badge", "logo", "emblem")),
    ("scenery",  ("scenery", "landscape", "mountain", "city")),
)

# The angles a good car Short really wants covered. Missing any of these is a
# content gap worth surfacing (badge/scenery are nice-to-have, not essential).
ESSENTIAL = ("front", "side", "rear", "interior", "action")


def angle_of(name: str) -> str:
    """Best-guess camera angle from a filename. Unknown -> 'other'."""
    low = Path(name).stem.lower()
    for angle, keys in _ANGLE_KEYWORDS:
        if any(k in low for k in keys):
            return angle
    return "other"


def plan_from_names(video_names: list[str], still_names: list[str], *,
                    target_cuts: int = DEFAULT_TARGET_CUTS,
                    known_sources: set[str] | None = None) -> dict:
    """Pure coverage/provenance math over already-clean filenames.

    `video_names` / `still_names` are the CLEAN pool (callers exclude _rejected/
    _quarantine). `known_sources` is the set of filenames with a recorded
    source+licence; any clip not in it is flagged unverified.
    Returns a plan dict (see keys below)."""
    known = known_sources or set()
    by_angle: dict[str, int] = {}
    for n in video_names:
        by_angle[angle_of(n)] = by_angle.get(angle_of(n), 0) + 1
    covered = set(by_angle)
    missing_essential = [a for a in ESSENTIAL if a not in covered]

    distinct = len(video_names)
    shortfall = max(0, target_cuts - distinct)
    unverified = sorted(n for n in video_names if n not in known)

    # "ready to render without repeating footage" = enough distinct clips AND no
    # essential angle entirely missing. Stills can pad duration but not identity.
    ready = shortfall == 0 and not missing_essential
    return {
        "clean_video": distinct,
        "stills": len(still_names),
        "target_cuts": target_cuts,
        "by_angle": dict(sorted(by_angle.items(), key=lambda kv: -kv[1])),
        "missing_essential": missing_essential,
        "shortfall_cuts": shortfall,
        "unverified_source": unverified,
        "ready": ready,
    }


def _known_sources(slug: str) -> set[str]:
    """Filenames with a recorded provenance: CC-still attributions.json +
    ingested-video footage_sources.json. Basename-keyed (paths vary by OS)."""
    car = paths.car_dir(slug)
    known: set[str] = set()
    for rel in ("images/attributions.json", "own/attributions.json",
                "own/footage_sources.json", "footage_sources.json"):
        p = car / rel
        if not p.exists():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — a bad provenance file just means 'unknown'
            continue
        rows = data if isinstance(data, list) else [
            {"file": k, **(v if isinstance(v, dict) else {})} for k, v in data.items()]
        for row in rows:
            f = row.get("file") if isinstance(row, dict) else None
            if f:
                known.add(Path(f).name)
    return known


def _clean_names(folder: Path, exts: set[str]) -> list[str]:
    """Top-level files of the given kinds — excludes _rejected/ and _quarantine/
    subdirs (those hold clips already pulled by the vision gate / vet)."""
    if not folder.exists():
        return []
    return sorted(p.name for p in folder.iterdir()
                  if p.is_file() and p.suffix.lower() in exts)


def assess(slug: str, target_cuts: int = DEFAULT_TARGET_CUTS) -> dict:
    """Read the car's real pool and return its footage plan."""
    car = paths.car_dir(slug)
    videos = _clean_names(car / "own", VIDEO_EXT)
    stills = _clean_names(car / "images", IMAGE_EXT) + _clean_names(car / "own", IMAGE_EXT)
    plan = plan_from_names(videos, stills, target_cuts=target_cuts,
                           known_sources=_known_sources(slug))
    plan["slug"] = slug
    return plan


def shopping_list(plan: dict) -> list[str]:
    """Human-readable, imperative gaps — what to shoot or source next."""
    lines: list[str] = []
    if plan["shortfall_cuts"]:
        lines.append(f"Need {plan['shortfall_cuts']} more distinct clip(s): "
                     f"{plan['clean_video']} clean vs {plan['target_cuts']} cuts "
                     f"(one clip per cut — the no-repeat rule).")
    if plan["missing_essential"]:
        lines.append("Missing essential angle(s): "
                     + ", ".join(plan["missing_essential"]) + ".")
    n_unv = len(plan["unverified_source"])
    if n_unv:
        shown = ", ".join(plan["unverified_source"][:4]) + ("…" if n_unv > 4 else "")
        lines.append(f"{n_unv} clip(s) have NO cleared source — verify licensing "
                     f"before ship (never ripped/watermarked ad footage): {shown}")
    if not lines:
        lines.append("Pool is render-ready: enough distinct clips, all essential "
                     "angles covered, provenance recorded.")
    return lines


def format_report(plan: dict) -> str:
    """A compact console report of a car's footage readiness."""
    slug = plan.get("slug", "?")
    head = "✅ READY" if plan["ready"] else "🔴 GAPS"
    ang = ", ".join(f"{a}:{n}" for a, n in plan["by_angle"].items()) or "(none)"
    out = [
        f"footage plan [{slug}] — {head}",
        f"  clean video : {plan['clean_video']}  (target {plan['target_cuts']} cuts)",
        f"  stills      : {plan['stills']}",
        f"  by angle    : {ang}",
    ]
    out += ["  • " + s for s in shopping_list(plan)]
    return "\n".join(out)


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(
        description="Footage cockpit: coverage + provenance + a shopping list for a car.")
    ap.add_argument("slug", help="car slug, e.g. tata-sierra")
    ap.add_argument("--cuts", type=int, default=DEFAULT_TARGET_CUTS,
                    help="target distinct cuts a Short needs (default 10)")
    ap.add_argument("--json", action="store_true", help="emit the raw plan as JSON")
    args = ap.parse_args()
    plan = assess(args.slug, target_cuts=args.cuts)
    if args.json:
        print(json.dumps(plan, indent=2))
    else:
        print(format_report(plan))


if __name__ == "__main__":
    main()
