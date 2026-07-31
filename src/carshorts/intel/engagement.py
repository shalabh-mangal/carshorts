"""Engagement engine — the one signal we can actually learn from today.

  python -m carshorts.intel.engagement                 # benchmark ours vs rivals
  python -m carshorts.intel.engagement --write         # + store rates on recipe cards

WHY THIS MATTERS MORE THAN IT LOOKS. Retention is currently unlearnable: the
per-second curves are gated behind a view threshold, YouTube lags 24-48h, and
the experiment ledger's views floor rejects every video we have. Engagement is
different — likes and comments are DIRECT COUNTS, present from the first view,
with no sampling and no processing lag. So engagement is the only lever we can
put under controlled experiment right now.

It is also the lever that matters for distribution: the Shorts recommender
expands a video that people react to, and ours are reacted to almost never
(measured 2026-07-23: ~0.65% like rate, ~0.13% comment rate, +1 subscriber
across 767 views).

The benchmark is the point. "0.65% is bad" was previously an ASSERTION — this
module measures rival like/comment rates from public data so the target is
evidence, not folklore. Rival engagement is public; their retention is not.

Comments-disabled videos report no commentCount at all; that is recorded as
None (unknown) rather than 0, so a disabled comment section never masquerades
as an audience that chose not to reply.
"""
from __future__ import annotations

import argparse
import datetime
import json
import statistics

from carshorts.core import paths

RECIPES = paths.RECIPES
REPORTS = paths.REPORTS
OUT = paths.ENGAGEMENT


def rates(video: dict) -> dict:
    """Per-video engagement rates as PERCENT of views. None when undefined."""
    views = video.get("views") or 0
    if views <= 0:
        return {"like_rate": None, "comment_rate": None}
    likes = video.get("likes")
    comments = video.get("comments")
    return {
        "like_rate": round(100 * likes / views, 3) if likes is not None else None,
        "comment_rate": round(100 * comments / views, 3) if comments is not None else None,
    }


def summarize_engagement(videos: list[dict], min_views: int = 0) -> dict:
    """Median engagement across a channel's recent uploads.

    Rates on a video with a handful of views are extremely noisy (one like on
    3 views = 33%), so min_views lets a caller demand a floor. Medians are used
    rather than means because a single viral video would otherwise dominate.
    """
    usable = [v for v in videos if (v.get("views") or 0) >= max(1, min_views)]
    if not usable:
        return {"videos": 0}
    likes, comments = [], []
    for v in usable:
        r = rates(v)
        if r["like_rate"] is not None:
            likes.append(r["like_rate"])
        if r["comment_rate"] is not None:
            comments.append(r["comment_rate"])
    return {
        "videos": len(usable),
        "median_like_rate": round(statistics.median(likes), 3) if likes else None,
        "median_comment_rate": round(statistics.median(comments), 3) if comments else None,
        "total_views": sum(v.get("views") or 0 for v in usable),
        "comments_disabled": sum(1 for v in usable if v.get("comments") is None),
    }


def write_rates_to_recipes(quiet: bool = False) -> int:
    """Store like_rate/comment_rate on each recipe so the experiment ledger can
    use them as a metric — these are testable at low view counts, unlike
    avg_view_pct."""
    updated = 0
    for path in sorted(RECIPES.glob("*.json")):
        try:
            rec = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        m = rec.get("metrics") or {}
        if not m.get("views"):
            continue
        r = rates({"views": m.get("views"), "likes": m.get("likes"),
                   "comments": m.get("comments")})
        m.update(r)
        rec["metrics"] = m
        path.write_text(json.dumps(rec, indent=2, ensure_ascii=False), encoding="utf-8")
        updated += 1
        if not quiet:
            print(f"  {rec.get('subject','?')[:22]:<24} like={r['like_rate']}%  "
                  f"comment={r['comment_rate']}%")
    return updated


def run(limit: int = 30, rival_min_views: int = 1000) -> dict:
    from carshorts.intel.competitors import _recent_videos, _resolve, load_watchlist
    from carshorts.publishing.ytauth import service

    yt = service("youtube", "v3")
    mine = yt.channels().list(part="snippet,contentDetails,statistics",
                              mine=True).execute()["items"][0]
    ours_videos = _recent_videos(yt, mine["contentDetails"]["relatedPlaylists"]["uploads"], limit)
    ours = {"title": mine["snippet"]["title"], **summarize_engagement(ours_videos)}

    rivals = []
    for ref in load_watchlist():
        ch = _resolve(yt, ref)
        if not ch:
            continue
        vids = _recent_videos(yt, ch["uploads"], limit)
        # a views floor on rivals only — their small videos would add noise,
        # while OURS are all small and must be shown honestly as they are
        rec = {"title": ch["title"], "subs": ch["subs"],
               **summarize_engagement(vids, min_views=rival_min_views)}
        rivals.append(rec)
        print(f"  {ch['title'][:28]:<30} like={rec.get('median_like_rate')}%  "
              f"comment={rec.get('median_comment_rate')}%")

    data = {"at": datetime.datetime.now().isoformat(timespec="seconds"),
            "ours": ours, "rivals": rivals}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return data


def _median(rivals: list[dict], key: str):
    vals = [r[key] for r in rivals if r.get(key) is not None]
    return round(statistics.median(vals), 3) if vals else None


def report(data: dict) -> str:
    ours, rivals = data["ours"], data["rivals"]
    rl, rc = _median(rivals, "median_like_rate"), _median(rivals, "median_comment_rate")
    ol, oc = ours.get("median_like_rate"), ours.get("median_comment_rate")

    def gap(mine, theirs):
        if mine is None or not theirs:
            return "—"
        return f"{mine / theirs:.2f}x" if theirs else "—"

    lines = [f"# Engagement benchmark — {datetime.date.today()}", "",
             "Likes and comments are DIRECT COUNTS — no sampling, no 24-48h lag, no",
             "view threshold. Unlike retention, this is measurable on our channel today,",
             "which makes it the only lever we can currently put under experiment.",
             "",
             f"Ours: **{ours.get('title')}** — {ours.get('videos', 0)} videos, "
             f"{ours.get('total_views', 0)} views", "",
             "| metric | ours | rivals (median) | ratio |", "|---|---|---|---|",
             f"| like rate % | {ol} | {rl} | {gap(ol, rl)} |",
             f"| comment rate % | {oc} | {rc} | {gap(oc, rc)} |", "",
             "## Per channel", "",
             "| channel | subs | videos | like % | comment % |", "|---|---|---|---|---|"]
    for r in sorted(rivals, key=lambda x: -(x.get("subs") or 0)):
        lines.append(f"| {r['title'][:26]} | {r.get('subs',0):,} | {r.get('videos',0)} "
                     f"| {r.get('median_like_rate')} | {r.get('median_comment_rate')} |")
    lines += ["", "## Caveats",
              "- Rival videos are filtered to a views floor; ours are not (we have none",
              "  that would clear it). Our rates therefore sit on very small denominators.",
              "- Engagement is correlated with, not proof of, distribution.",
              "- Comments-disabled videos are recorded as unknown, never as zero."]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="Benchmark engagement; store rates on recipes.")
    ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--rival-min-views", type=int, default=1000)
    ap.add_argument("--write", action="store_true",
                    help="Also store like_rate/comment_rate on recipe cards.")
    args = ap.parse_args()

    print("engagement benchmark — sampling watchlist")
    data = run(limit=args.limit, rival_min_views=args.rival_min_views)
    text = report(data)
    REPORTS.mkdir(parents=True, exist_ok=True)
    out = REPORTS / f"engagement-{datetime.date.today()}.md"
    out.write_text(text, encoding="utf-8")
    print("\n" + text)
    if args.write:
        print("\nstoring rates on recipe cards:")
        n = write_rates_to_recipes()
        print(f"  {n} recipe(s) updated — like_rate/comment_rate now usable as "
              f"experiment metrics")
    print(f"\nreport -> {out}")


if __name__ == "__main__":
    main()
