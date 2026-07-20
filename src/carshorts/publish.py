"""Publish a video to YouTube via the Data API v3 (the last pipeline stage).

ONE-TIME SETUP (only you can do this — it's your Google account):
  1. console.cloud.google.com -> create a project.
  2. "APIs & Services" -> Library -> enable "YouTube Data API v3".
  3. OAuth consent screen -> External -> add your Google account as a Test user.
  4. Credentials -> Create -> OAuth client ID -> Desktop app -> download JSON.
     Save it as  client_secret.json  in the project root.
  5. pip install -e ".[publish]"

USAGE:
  python -m carshorts.publish out/nexon_features.mp4 \
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

_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
_CLIENT_SECRET = "client_secret.json"
_TOKEN = "youtube_token.json"


def _get_service():
    """Authorize (cached) and return a YouTube API client. Lazy imports so the
    rest of the project doesn't need the Google libraries installed."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None
    if Path(_TOKEN).exists():
        creds = Credentials.from_authorized_user_file(_TOKEN, _SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not Path(_CLIENT_SECRET).exists():
                raise SystemExit(
                    f"Missing {_CLIENT_SECRET}. Follow the one-time setup in "
                    "publish.py (Google Cloud OAuth client, Desktop app).")
            flow = InstalledAppFlow.from_client_secrets_file(_CLIENT_SECRET, _SCOPES)
            creds = flow.run_local_server(port=0)
        Path(_TOKEN).write_text(creds.to_json())
    return build("youtube", "v3", credentials=creds)


def upload(video_path: str, title: str, description: str = "", tags=None,
           privacy: str = "private", made_for_kids: bool = False,
           category_id: str = "2") -> str:
    """Upload a video; return the new video id. category 2 = Autos & Vehicles."""
    from googleapiclient.http import MediaFileUpload

    service = _get_service()
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
    args = p.parse_args()

    description = (Path(args.description_file).read_text() if args.description_file
                  else args.description)
    tags = [t.strip() for t in args.tags.split(",") if t.strip()]
    upload(args.video, args.title, description, tags, args.privacy, args.made_for_kids)


if __name__ == "__main__":
    main()
