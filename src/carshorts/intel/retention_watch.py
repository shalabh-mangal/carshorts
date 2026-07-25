"""Retention watch — closes the learning loop the moment YouTube releases data.

  python -m carshorts.intel.retention_watch            # run once
  python -m carshorts.intel.retention_watch --quiet    # for scheduled runs

YouTube gates the per-second `audienceWatchRatio` curve behind a minimum-views
threshold AND lags 24-48h, so a freshly published Short has no curve for days.
Until it appears, retention is a single flat number (avg view %) that tells you
nothing about WHERE viewers leave — which is the only thing worth knowing.

This watcher refreshes every linked recipe card, and the FIRST time a curve
appears it maps the drop-offs onto that video's script BEATS (via the render
manifest) and journals the finding to data/retention_log.jsonl.

Deliberately does NOT call an LLM. It records evidence; it does not invent
lessons from a thin sample — that stays a supervisor decision (see agents/
TASTE.md: "a flagged doubt is worth more than a confident miss").
"""
from __future__ import annotations

import argparse
import datetime
import json
from pathlib import Path

from carshorts.intel.analyze import _fetch_metrics

RECIPES = Path("data/recipes")
JOURNAL = Path("data/retention_log.jsonl")
REPORTS = Path("data/reports")


def _manifest_for(recipe: dict) -> Path | None:
    """Find the render manifest for a recipe, if one survives locally.

    Renders write it beside the mp4; the curated mirror in context/manifests/
    is the fallback when out/ has been cleaned (it is gitignored).
    """
    out = recipe.get("out") or ""
    if out:
        beside = Path(out).with_suffix(".manifest.json")
        if beside.exists():
            return beside
        mirror = Path("context/manifests") / beside.name
        if mirror.exists():
            return mirror
    return None


def beat_drops(curve: list, manifest_path: Path) -> tuple[dict, str]:
    """Map a retention curve onto script beats -> ({role: audience lost}, worst).

    curve is [[elapsed_ratio, audience_ratio], ...]. Beat boundaries come from
    the manifest's section durations, so a drop is attributed to whichever beat
    was ON SCREEN when the audience left.
    """
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    sections = manifest.get("sections", [])
    if not sections or not curve:
        return {}, ""
    total = sum(s["duration"] for s in sections)
    bounds, acc = [], 0.0
    for s in sections:
        acc += s["duration"]
        bounds.append((s["role"], acc))

    drops: dict[str, float] = {}
    prev = None
    for elapsed, watch in curve:
        t = float(elapsed) * total
        role = next((rl for rl, end in bounds if t <= end), bounds[-1][0])
        if prev is not None:
            drops[role] = drops.get(role, 0.0) + max(0.0, prev - float(watch))
        prev = float(watch)
    drops = {k: round(v, 4) for k, v in drops.items()}
    # A beat is only "worst" if the audience ACTUALLY left during it. A flat
    # curve must not nominate a scapegoat — naming a beat nobody dropped on
    # would send the writer to rewrite something that was working.
    worst = max(drops, key=drops.get) if any(v > 0 for v in drops.values()) else ""
    return drops, worst


def run(quiet: bool = False) -> list[dict]:
    """Refresh metrics on every linked recipe; report newly-arrived curves."""
    findings: list[dict] = []
    now = datetime.datetime.now().isoformat(timespec="seconds")

    for path in sorted(RECIPES.glob("*.json")):
        recipe = json.loads(path.read_text(encoding="utf-8"))
        vid = recipe.get("video_id")
        if not vid:
            continue
        had_curve = bool((recipe.get("metrics") or {}).get("retention_curve"))
        metrics = _fetch_metrics(vid)
        if not metrics:
            if not quiet:
                print(f"  {recipe.get('subject','?')[:20]:<20} {vid}  metrics unavailable")
            continue

        curve = metrics.get("retention_curve")
        entry = {
            "at": now, "video_id": vid, "subject": recipe.get("subject"),
            "views": metrics.get("views"),
            "avg_view_pct": metrics.get("avg_view_pct"),
            "curve": "new" if (curve and not had_curve) else ("yes" if curve else "no"),
        }

        manifest = _manifest_for(recipe)
        if curve and manifest:
            drops, worst = beat_drops(curve, manifest)
            if drops:
                metrics["drop_by_beat"] = drops
                metrics["worst_beat"] = worst
                entry["drop_by_beat"] = drops
                entry["worst_beat"] = worst
        elif curve and not manifest:
            entry["note"] = "curve available but no manifest — beats unmappable"

        recipe["metrics"] = metrics
        path.write_text(json.dumps(recipe, indent=2, ensure_ascii=False),
                        encoding="utf-8")
        findings.append(entry)

        if not quiet:
            pct = metrics.get("avg_view_pct")
            mark = "🆕 CURVE" if entry["curve"] == "new" else ("curve" if curve else "     ")
            print(f"  {str(recipe.get('subject'))[:20]:<20} {vid}  "
                  f"views={metrics.get('views'):<5} "
                  f"avg%={(f'{pct:.1f}' if pct else '-'):<6} {mark}"
                  + (f"  worst_beat={entry.get('worst_beat')}" if entry.get("worst_beat") else "")
                  + (f"  ({entry['note']})" if entry.get("note") else ""))

    if findings:
        JOURNAL.parent.mkdir(parents=True, exist_ok=True)
        with JOURNAL.open("a", encoding="utf-8") as fh:
            for entry in findings:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    fresh = [f for f in findings if f["curve"] == "new"]
    if fresh and not quiet:
        print(f"\n🆕 {len(fresh)} retention curve(s) arrived — beat-level diagnosis "
              f"is now possible. Review before changing the script formula.")
    return findings


def main() -> None:
    ap = argparse.ArgumentParser(description="Poll for retention curves; map drops to beats.")
    ap.add_argument("--quiet", action="store_true", help="Only print when a curve is new.")
    args = ap.parse_args()
    if not args.quiet:
        print("retention watch — refreshing linked recipes")
    run(quiet=args.quiet)


if __name__ == "__main__":
    main()
