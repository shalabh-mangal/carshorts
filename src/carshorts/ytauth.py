"""Shared YouTube OAuth — one cached token for both upload and analytics.

Scopes cover uploading videos and reading analytics, so a single browser
consent (see the setup steps in publish.py) powers both `publish` and
`analytics`. Token is cached in youtube_token.json.
"""
from __future__ import annotations

from pathlib import Path

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]
CLIENT_SECRET = "client_secret.json"
TOKEN = "youtube_token.json"


def credentials():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None
    if Path(TOKEN).exists():
        creds = Credentials.from_authorized_user_file(TOKEN, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not Path(CLIENT_SECRET).exists():
                raise SystemExit(
                    f"Missing {CLIENT_SECRET}. Follow the one-time Google Cloud "
                    "OAuth setup documented at the top of publish.py.")
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET, SCOPES)
            creds = flow.run_local_server(port=0)
        Path(TOKEN).write_text(creds.to_json())
    return creds


def service(api: str, version: str):
    from googleapiclient.discovery import build

    return build(api, version, credentials=credentials())
