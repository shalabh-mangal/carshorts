"""Read YouTube analytics for a video (or the channel) so scripts can be tuned.

Needs the same one-time Google OAuth as publish.py (shared token). Then:

  python -m carshorts.analytics --video VamhQZHDgSU
  python -m carshorts.analytics                 # last 28 days, channel-wide

Reports the retention signals that actually matter for Shorts: views, average
view duration, and average view PERCENTAGE (how far through people watch — the
hook/pacing signal).
"""
from __future__ import annotations

import argparse
import datetime as _dt

from .ytauth import service


def _channel_id(youtube) -> str:
    resp = youtube.channels().list(part="id", mine=True).execute()
    return resp["items"][0]["id"]


def video_report(video_id: str) -> None:
    youtube = service("youtube", "v3")
    meta = youtube.videos().list(part="snippet,statistics", id=video_id).execute()
    if not meta.get("items"):
        raise SystemExit(f"No video found for id {video_id}")
    item = meta["items"][0]
    stats = item.get("statistics", {})
    print(f"# {item['snippet']['title']}")
    print(f"  views={stats.get('viewCount', '?')}  likes={stats.get('likeCount', '?')}  "
          f"comments={stats.get('commentCount', '?')}")

    yta = service("youtubeAnalytics", "v2")
    today = _dt.date.today().isoformat()
    rep = yta.reports().query(
        ids=f"channel=={_channel_id(youtube)}",
        startDate="2005-02-14", endDate=today,
        metrics="views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage",
        filters=f"video=={video_id}",
    ).execute()
    rows = rep.get("rows", [])
    if rows:
        _v, _mins, avg_dur, avg_pct = rows[0]
        print(f"  avg view duration = {avg_dur}s   avg view % = {avg_pct:.1f}%  "
              f"(the hook/pacing signal)")
        if avg_pct < 50:
            print("  -> low completion: tighten the hook + trim length.")


def channel_report(days: int = 28) -> None:
    youtube = service("youtube", "v3")
    yta = service("youtubeAnalytics", "v2")
    end = _dt.date.today()
    start = end - _dt.timedelta(days=days)
    rep = yta.reports().query(
        ids=f"channel=={_channel_id(youtube)}",
        startDate=start.isoformat(), endDate=end.isoformat(),
        metrics="views,estimatedMinutesWatched,averageViewPercentage,subscribersGained",
        dimensions="day",
    ).execute()
    print(f"# Channel — last {days} days")
    for row in rep.get("rows", []):
        print("  " + "  ".join(str(c) for c in row))


def main() -> None:
    p = argparse.ArgumentParser(description="Read YouTube analytics.")
    p.add_argument("--video", help="Video id to report on.")
    p.add_argument("--days", type=int, default=28, help="Channel window if no --video.")
    args = p.parse_args()
    if args.video:
        video_report(args.video)
    else:
        channel_report(args.days)


if __name__ == "__main__":
    main()
