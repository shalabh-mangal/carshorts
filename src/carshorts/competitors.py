"""Competitor intel — the system finally sees something other than itself.

  python -m carshorts.competitors                    # pull + benchmark + report
  python -m carshorts.competitors --add @motoroctane # extend the watch list
  python -m carshorts.competitors --limit 40         # deeper history per channel

Until now the brain learned only from our own 5 videos. That is not enough to
"crack the algorithm" — you cannot learn a system you cannot observe. This pulls
PUBLIC signals from rival car channels and benchmarks ours against them, so
choices (length, title shape, cadence, topic) have an external reference.

HONEST LIMITS — stated because a benchmark that overclaims is worse than none:
  - Competitor RETENTION AND CTR ARE PRIVATE. Nothing here can see them. We see
    views/likes/comments/duration/titles/cadence and nothing more.
  - Views are an OUTCOME of channel size and age, not a tactic. A 2M-sub channel
    getting 100k views tells us nothing we can copy. What IS transferable is
    SHAPE: how long, how often, how titles are built, Shorts vs long-form mix.
  - Correlation only. This engine describes what rivals do; it never asserts
    that doing it will work for us. That is the experiment ledger's job.

QUOTA: uses channels.list(forHandle) + playlistItems + videos — about 3-5 units
per channel. It deliberately avoids search.list, which costs 100 units a call
against a 10,000/day budget.
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import statistics
from pathlib import Path

WATCHLIST = Path("data/competitors.json")
INTEL = Path("data/competitor_intel.json")
REPORTS = Path("data/reports")

# Seed list — the owner curates this. Handles that don't resolve are reported,
# never silently dropped.
DEFAULT_WATCHLIST = ["@motoroctane", "@carwow", "@PowerDrift", "@autocarindia"]

_EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")


def iso_duration_seconds(iso: str) -> int:
    """PT#M#S / PT#H#M#S -> seconds."""
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return 0
    h, mi, s = (int(g or 0) for g in m.groups())
    return h * 3600 + mi * 60 + s


def title_features(title: str) -> dict:
    """Structural features of a title — the transferable part of a rival's
    craft (unlike their view count, which is a function of their audience)."""
    words = title.split()
    caps = [w for w in words if len(w) > 2 and w.isupper()]
    return {
        "chars": len(title),
        "words": len(words),
        "is_question": "?" in title,
        "has_number": bool(re.search(r"\d", title)),
        "has_emoji": bool(_EMOJI.search(title)),
        "caps_words": len(caps),
        "has_colon": ":" in title,
    }


def summarize(videos: list[dict]) -> dict:
    """Aggregate a channel's recent uploads into comparable shape metrics."""
    if not videos:
        return {}
    views = sorted(v["views"] for v in videos)
    durations = [v["duration_s"] for v in videos]
    shorts = [v for v in videos if v["duration_s"] <= 180]
    feats = [title_features(v["title"]) for v in videos]
    dates = sorted(v["published"] for v in videos if v.get("published"))

    per_week = None
    if len(dates) >= 2:
        span_days = max(1.0, (dates[-1] - dates[0]).total_seconds() / 86400)
        per_week = round(len(dates) / span_days * 7, 1)

    def pct(key):
        return round(100 * sum(1 for f in feats if f[key]) / len(feats))

    return {
        "videos_sampled": len(videos),
        "median_views": int(statistics.median(views)),
        "max_views": max(views),
        "median_duration_s": int(statistics.median(durations)),
        "short_form_share_pct": round(100 * len(shorts) / len(videos)),
        "median_shortform_duration_s": (
            int(statistics.median([v["duration_s"] for v in shorts])) if shorts else None),
        "uploads_per_week": per_week,
        "title_median_chars": int(statistics.median([f["chars"] for f in feats])),
        "title_question_pct": pct("is_question"),
        "title_number_pct": pct("has_number"),
        "title_emoji_pct": pct("has_emoji"),
        "title_colon_pct": pct("has_colon"),
    }


def load_watchlist() -> list[str]:
    if WATCHLIST.exists():
        try:
            data = json.loads(WATCHLIST.read_text(encoding="utf-8"))
            return list(data.get("channels", DEFAULT_WATCHLIST))
        except Exception:  # noqa: BLE001
            pass
    return list(DEFAULT_WATCHLIST)


def save_watchlist(channels: list[str]) -> None:
    WATCHLIST.parent.mkdir(parents=True, exist_ok=True)
    WATCHLIST.write_text(json.dumps(
        {"_note": "Channels to benchmark against. Handles (@x) or channel IDs (UC...).",
         "channels": channels}, indent=2), encoding="utf-8")


def _resolve(yt, ref: str) -> dict | None:
    """Handle (@x) or channel id (UC...) -> channel record. 1 quota unit."""
    try:
        if ref.startswith("UC"):
            resp = yt.channels().list(part="snippet,statistics,contentDetails", id=ref).execute()
        else:
            resp = yt.channels().list(part="snippet,statistics,contentDetails",
                                      forHandle=ref.lstrip("@")).execute()
        items = resp.get("items") or []
        if not items:
            return None
        ch = items[0]
        return {"ref": ref, "id": ch["id"], "title": ch["snippet"]["title"],
                "subs": int(ch["statistics"].get("subscriberCount", 0) or 0),
                "total_views": int(ch["statistics"].get("viewCount", 0) or 0),
                "uploads": ch["contentDetails"]["relatedPlaylists"]["uploads"]}
    except Exception:  # noqa: BLE001 — one bad handle must not kill the sweep
        return None


def _recent_videos(yt, uploads_playlist: str, limit: int) -> list[dict]:
    ids, page = [], None
    while len(ids) < limit:
        r = yt.playlistItems().list(part="contentDetails", playlistId=uploads_playlist,
                                    maxResults=min(50, limit - len(ids)),
                                    pageToken=page).execute()
        ids += [i["contentDetails"]["videoId"] for i in r.get("items", [])]
        page = r.get("nextPageToken")
        if not page:
            break

    out = []
    for start in range(0, len(ids), 50):
        chunk = ids[start:start + 50]
        r = yt.videos().list(part="snippet,statistics,contentDetails",
                             id=",".join(chunk)).execute()
        for it in r.get("items", []):
            pub = it["snippet"].get("publishedAt", "")
            try:
                published = datetime.datetime.fromisoformat(pub.replace("Z", "+00:00")).replace(tzinfo=None)
            except ValueError:
                published = None
            st = it.get("statistics", {})
            out.append({
                "id": it["id"], "title": it["snippet"]["title"], "published": published,
                "views": int(st.get("viewCount", 0) or 0),
                "likes": int(st.get("likeCount", 0) or 0),
                # commentCount is absent when comments are disabled — distinguish
                # that from "zero comments", which is a real engagement signal.
                "comments": (int(st["commentCount"]) if "commentCount" in st else None),
                "duration_s": iso_duration_seconds(it["contentDetails"].get("duration", "")),
            })
    return out


def run(limit: int = 30) -> dict:
    from .ytauth import service
    yt = service("youtube", "v3")

    # ours, measured the same way so the comparison is apples-to-apples
    mine = yt.channels().list(part="snippet,statistics,contentDetails", mine=True).execute()["items"][0]
    ours_videos = _recent_videos(yt, mine["contentDetails"]["relatedPlaylists"]["uploads"], limit)
    ours = {"ref": "US", "title": mine["snippet"]["title"],
            "subs": int(mine["statistics"].get("subscriberCount", 0) or 0),
            "total_views": int(mine["statistics"].get("viewCount", 0) or 0),
            **summarize(ours_videos)}

    rivals, unresolved = [], []
    for ref in load_watchlist():
        ch = _resolve(yt, ref)
        if not ch:
            unresolved.append(ref)
            print(f"  [unresolved] {ref}")
            continue
        vids = _recent_videos(yt, ch["uploads"], limit)
        rec = {**{k: ch[k] for k in ("ref", "id", "title", "subs", "total_views")},
               **summarize(vids)}
        rivals.append(rec)
        print(f"  {ch['title'][:30]:<32} subs={ch['subs']:<10} "
              f"sampled={rec.get('videos_sampled', 0)}")

    intel = {"at": datetime.datetime.now().isoformat(timespec="seconds"),
             "ours": ours, "rivals": rivals, "unresolved": unresolved}
    INTEL.parent.mkdir(parents=True, exist_ok=True)
    INTEL.write_text(json.dumps(intel, indent=2, ensure_ascii=False, default=str),
                     encoding="utf-8")
    return intel


def _median_of(rivals: list[dict], key: str):
    vals = [r[key] for r in rivals if r.get(key) is not None]
    return round(statistics.median(vals), 1) if vals else None


def report(intel: dict) -> str:
    ours, rivals = intel["ours"], intel["rivals"]
    rows = [
        ("short-form share %", "short_form_share_pct"),
        ("median short-form length (s)", "median_shortform_duration_s"),
        ("uploads / week", "uploads_per_week"),
        ("title median chars", "title_median_chars"),
        ("titles with a number %", "title_number_pct"),
        ("titles as question %", "title_question_pct"),
        ("titles with emoji %", "title_emoji_pct"),
    ]
    lines = [f"# Competitor intel — {datetime.date.today()}", "",
             "Public signals only. **Rival retention and CTR are private and are not "
             "shown here.** Views are an outcome of audience size, not a copyable "
             "tactic — compare SHAPE (length, cadence, title construction), not scale.",
             "",
             f"Ours: **{ours.get('title')}** — {ours.get('subs')} subs, "
             f"{ours.get('videos_sampled', 0)} videos sampled", "",
             "| metric | ours | rivals (median) |", "|---|---|---|"]
    for label, key in rows:
        lines.append(f"| {label} | {ours.get(key)} | {_median_of(rivals, key)} |")

    lines += ["", "## Channels sampled", "",
              "| channel | subs | sampled | median views | uploads/wk | median short (s) |",
              "|---|---|---|---|---|---|"]
    for r in sorted(rivals, key=lambda x: -x.get("subs", 0)):
        lines.append(f"| {r['title'][:28]} | {r['subs']:,} | {r.get('videos_sampled',0)} "
                     f"| {r.get('median_views','-')} | {r.get('uploads_per_week','-')} "
                     f"| {r.get('median_shortform_duration_s','-')} |")
    if intel.get("unresolved"):
        lines += ["", f"Unresolved handles (fix in {WATCHLIST}): "
                      + ", ".join(intel["unresolved"])]
    lines += ["", "## How to use this",
              "- Differences here are HYPOTHESES, not instructions. Feed one at a time",
              "  into the experiment calendar and let the ledger decide.",
              "- Do not chase rival view counts; chase the shape choices you can copy."]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="Benchmark our channel against rival car channels.")
    ap.add_argument("--add", metavar="HANDLE", help="Add a channel (@handle or UC...id).")
    ap.add_argument("--limit", type=int, default=30, help="Recent videos per channel.")
    args = ap.parse_args()

    if args.add:
        channels = load_watchlist()
        if args.add not in channels:
            channels.append(args.add)
            save_watchlist(channels)
        print(f"watchlist: {channels}")
        return

    print("competitor intel — sampling watchlist")
    intel = run(limit=args.limit)
    text = report(intel)
    REPORTS.mkdir(parents=True, exist_ok=True)
    out = REPORTS / f"competitors-{datetime.date.today()}.md"
    out.write_text(text, encoding="utf-8")
    print("\n" + text)
    print(f"\nreport -> {out}")


if __name__ == "__main__":
    main()
