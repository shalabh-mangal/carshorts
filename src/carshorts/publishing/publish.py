"""Publish a video to YouTube via the Data API v3 (the last pipeline stage).

ONE-TIME SETUP (only you can do this — it's your Google account):
  1. console.cloud.google.com -> create a project.
  2. "APIs & Services" -> Library -> enable "YouTube Data API v3".
  3. OAuth consent screen -> External -> add your Google account as a Test user.
  4. Credentials -> Create -> OAuth client ID -> Desktop app -> download JSON.
     Save it as  client_secret.json  in the project root.
  5. pip install -e ".[publish]"

USAGE:
  python -m carshorts.publishing.publish out/nexon_features.mp4 \
      --title "Tata Nexon in 60s" --description-file desc.txt \
      --tags TataNexon,CarShorts,Shorts --privacy public

First run opens a browser to authorize; the token is cached in youtube_token.json
so later runs are non-interactive.

Notes / honest caveats:
  - A brand-new / unverified channel may have API uploads forced to PRIVATE by
    YouTube until you verify the channel — that is YouTube's anti-spam rule, not
    a bug here.
  - Free API quota is ~10,000 units/day; an upload costs ~1,600, so ~6/day.
  - Custom Short thumbnails still need the mobile app; this sets video + metadata.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from carshorts.core import paths
from carshorts.publishing.ytauth import service as _yt_service


def upload(video_path: str, title: str, description: str = "", tags=None,
           privacy: str = "private", made_for_kids: bool = False,
           category_id: str = "2", thumbnail: str | None = None) -> str:
    """Upload a video; return the new video id. category 2 = Autos & Vehicles."""
    from googleapiclient.http import MediaFileUpload

    service = _yt_service("youtube", "v3")
    body = {
        "snippet": {
            "title": title[:100],
            "description": description,
            "tags": tags or [],
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": made_for_kids,
        },
    }
    media = MediaFileUpload(video_path, chunksize=-1, resumable=True, mimetype="video/mp4")
    request = service.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"   upload {int(status.progress() * 100)}%")
    video_id = response["id"]
    if thumbnail and Path(thumbnail).exists():
        try:
            service.thumbnails().set(videoId=video_id,
                                     media_body=MediaFileUpload(thumbnail)).execute()
            print("   thumbnail set")
        except Exception as exc:  # noqa: BLE001 — channel may lack custom-thumb perms
            print(f"   thumbnail not set ({exc}); set it in the mobile app")
    try:   # link the upload to its recipe card so the analyst can join metrics
        import json as _json
        rp = paths.RECIPES / (Path(video_path).stem + ".json")
        if rp.exists():
            rec = _json.loads(rp.read_text())
            rec["video_id"] = video_id
            rp.write_text(_json.dumps(rec, indent=2, ensure_ascii=False))
            print(f"   recipe linked: {rp.name}")
    except Exception:  # noqa: BLE001
        pass
    print(f"Done -> https://youtube.com/watch?v={video_id}  (privacy={privacy})")
    return video_id


def main() -> None:
    p = argparse.ArgumentParser(description="Upload a video to YouTube.")
    p.add_argument("video", help="Path to the MP4.")
    p.add_argument("--title", required=True)
    p.add_argument("--description", default="")
    p.add_argument("--description-file", help="Read description from a file (overrides --description).")
    p.add_argument("--tags", default="", help="Comma-separated tags.")
    p.add_argument("--privacy", default="private", choices=["private", "unlisted", "public"])
    p.add_argument("--made-for-kids", action="store_true")
    p.add_argument("--thumbnail", help="PNG/JPG to set as the video thumbnail.")
    args = p.parse_args()

    description = (Path(args.description_file).read_text() if args.description_file
                  else args.description)
    if len(description) > 4900:   # YouTube hard cap 5000 — truncate at a line break
        description = description[:4900].rsplit("\n", 1)[0] + "\n…"
        print(f"   description truncated to {len(description)} chars (YouTube cap)")
    description = description.replace("<", "(").replace(">", ")")  # forbidden chars
    tags = [t.strip() for t in args.tags.split(",") if t.strip()]
    upload(args.video, args.title, description, tags, args.privacy, args.made_for_kids,
           thumbnail=args.thumbnail)


if __name__ == "__main__":
    main()
