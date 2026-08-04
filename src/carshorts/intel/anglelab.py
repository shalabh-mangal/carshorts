"""Angle Lab — closes the Script Studio learning loop.

Each render is tagged by produce with its script_format + USP. This reads the
render recipes + their YouTube metrics, ranks which FORMATS actually perform, and
writes a single [angle-lab] data-learning. The angle miner
(writing/scriptbrain.mine_angles) reads the learnings, so winning formats become
priors — the brain gets better at choosing angles over time.

Evaluate-only and idempotent (replaces its prior entry). No-ops until enough
tagged videos have metrics, so it never invents a lesson from a thin sample.

  carshorts anglelab            # rank formats, update learnings when ready
  carshorts anglelab --dry-run  # print only, don't write
"""
from __future__ import annotations

import argparse
import datetime
import json
from collections import defaultdict

from carshorts.core import paths

TAG = "[high][data][angle-lab]"


def _recipes():
    for p in sorted(paths.RECIPES.glob("*.json")):
        try:
            yield json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — a bad recipe is skipped
            continue


def summarize(min_videos: int = 4, apply: bool = True) -> dict:
    """Rank script formats by average views (and retention where present). Writes a
    [angle-lab] learning once >= min_videos tagged videos have metrics."""
    rows = []
    for r in _recipes():
        fmt = r.get("script_format")
        m = r.get("metrics") or {}
        views = m.get("views")
        if fmt and fmt != "mix" and views is not None:
            rows.append({"format": fmt, "views": views, "ret": m.get("avg_view_pct")})
    if len(rows) < min_videos:
        print(f"angle-lab: {len(rows)} tagged video(s) with metrics — need "
              f"{min_videos}; skipping (no lesson from a thin sample).")
        return {"videos": len(rows), "ready": False}

    agg: dict[str, list] = defaultdict(list)
    for r in rows:
        agg[r["format"]].append(r)
    stats = []
    for fmt, rs in agg.items():
        vv = [x["views"] for x in rs]
        rr = [x["ret"] for x in rs if x["ret"] is not None]
        stats.append({"format": fmt, "n": len(rs),
                      "avg_views": sum(vv) / len(vv),
                      "avg_ret": (sum(rr) / len(rr)) if rr else None})
    stats.sort(key=lambda s: s["avg_views"], reverse=True)
    best, worst = stats[0], stats[-1]
    parts = []
    for s in stats:
        seg = f"{s['format']} ~{int(s['avg_views'])} views"
        if s["avg_ret"] is not None:
            seg += f"/{s['avg_ret']:.0f}% ret"
        parts.append(seg + f" (n={s['n']})")
    line = (f"{TAG} Format performance across {len(rows)} videos: " + "; ".join(parts)
            + f". Prefer {best['format']} for new angles"
            + ("" if best is worst else f"; {worst['format']} underperforms") + ".")
    if apply:
        _write_learning(line)
    print(line)
    return {"videos": len(rows), "ready": True, "stats": stats, "learning": line}


def _write_learning(line: str) -> None:
    p = paths.LEARNINGS
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — start fresh if the file is missing/bad
        data = {"craft_playbook": [], "data_learnings": []}
    dl = [x for x in data.get("data_learnings", []) if "[angle-lab]" not in x]  # replace prior
    dl.append(line)
    data["data_learnings"] = dl
    data["updated"] = datetime.date.today().isoformat()
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description="Rank script formats by performance; feed the angle miner.")
    ap.add_argument("--min-videos", type=int, default=4)
    ap.add_argument("--dry-run", action="store_true", help="Print only; don't write the learning.")
    args = ap.parse_args()
    summarize(min_videos=args.min_videos, apply=not args.dry_run)


if __name__ == "__main__":
    main()
