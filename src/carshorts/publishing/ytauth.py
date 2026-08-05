"""Shared YouTube OAuth — one cached token for both upload and analytics.

Scopes cover uploading videos and reading analytics, so a single browser
consent (see the setup steps in publish.py) powers both `publish` and
`analytics`. Token is cached in youtube_token.json.
"""
from __future__ import annotations

import os
from pathlib import Path

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    # post the auto poll-comment on our own uploads (commentThreads.insert).
    # NOTE: adding a scope invalidates the cached token — re-auth once.
    "https://www.googleapis.com/auth/youtube.force-ssl",
]
CLIENT_SECRET = "client_secret.json"
TOKEN = "youtube_token.json"


def credentials():
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None
    if Path(TOKEN).exists():
        creds = Credentials.from_authorized_user_file(TOKEN, SCOPES)
    if creds and creds.valid:
        return creds

    # Try a silent refresh first. A "Testing"-mode OAuth app has its refresh
    # token REVOKED by Google after ~7 days, so refresh raises invalid_grant —
    # in that case drop the dead token and fall through to a fresh browser
    # consent rather than crashing the publish/analytics run.
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            Path(TOKEN).write_text(creds.to_json())
            return creds
        except RefreshError:
            Path(TOKEN).unlink(missing_ok=True)
            creds = None

    if not Path(CLIENT_SECRET).exists():
        raise SystemExit(
            f"Missing {CLIENT_SECRET}. Follow the one-time Google Cloud "
            "OAuth setup documented at the top of publish.py.")
    # Opens a browser for the OWNER to sign in + consent. Interactive by design —
    # never run this from an unattended/background job; re-auth is a human step.
    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET, SCOPES)
    creds = flow.run_local_server(port=0)
    Path(TOKEN).write_text(creds.to_json())
    return creds


def service(api: str, version: str):
    from googleapiclient.discovery import build

    return build(api, version, credentials=credentials())


def channel_identity(youtube) -> tuple[str, str]:
    """(channel_id, title) of the currently authed channel."""
    r = youtube.channels().list(part="snippet", mine=True).execute()
    it = (r.get("items") or [{}])[0]
    return it.get("id", ""), (it.get("snippet") or {}).get("title", "")


def assert_channel(youtube, expected: str | None = None) -> tuple[str, str]:
    """Refuse to act unless the authed channel is the EXPECTED one.

    A wrong-channel token once published a Short to the wrong account, publicly.
    `expected` is a channel id ('UC…') OR a case-insensitive name substring;
    it defaults to the CARSHORTS_CHANNEL env var, then to 'carshort'. Returns
    (id, title) on match; raises RuntimeError otherwise so the upload aborts."""
    expected = (expected or os.environ.get("CARSHORTS_CHANNEL") or "carshort").strip()
    cid, title = channel_identity(youtube)
    if expected == cid or expected.lower() in (title or "").lower():
        return cid, title
    raise RuntimeError(
        f"CHANNEL GUARD: authed as {title!r} ({cid}), but expected {expected!r}. "
        "Refusing to upload to the wrong channel — re-auth to carshorts (delete "
        "youtube_token.json and re-run) or set CARSHORTS_CHANNEL to the right id/name.")
