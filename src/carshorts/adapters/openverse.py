"""Openverse image source — the widest free, monetization-safe still pool.

Openverse (openverse.org) indexes 800M+ openly licensed / public-domain images
across Wikimedia, Flickr, museums and more, behind one license-filterable API
with no key required. For a given car it surfaces far more correct-vehicle stills
than a single-site search does — which is the whole game for a stills-first
video (motion from generic b-roll, identity from these stills).

Two guarantees, mirroring WikimediaImageSource:
  1. LICENSE — only commercial-AND-derivative-safe licences are requested
     (cc0, pdm, by, by-sa). `nd` (no-derivatives) is excluded because we crop and
     Ken-Burns the image, and `nc` (non-commercial) is excluded because the
     channel is monetized. So every kept image is safe to edit and to monetize.
  2. ATTRIBUTION — author + licence + source page are recorded (merged into the
     shared attributions.json) so CC-BY/BY-SA credit lands in the description.

No image is invented and no credit is fabricated; a plate/watermark/wrong-vehicle
check still runs downstream (assetvet) before anything reaches the render pool.
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from carshorts.adapters.footage import (
    _SKIP_TITLE,
    _SSL_CONTEXT,
    _USER_AGENT,
    FootageSource,
    merge_attributions,
)

# Commercial + derivative safe. Deliberately omits by-nc* (non-commercial) and
# by-nd / by-nc-nd (no-derivatives) — both would be a monetization or editing
# breach for this channel.
_SAFE_LICENSES = "cc0,pdm,by,by-sa"


class OpenverseImageSource(FootageSource):
    API = "https://api.openverse.org/v1/images/"

    def _search(self, subject: str, page_size: int) -> list[dict]:
        params = urllib.parse.urlencode({
            "q": subject,
            "license": _SAFE_LICENSES,
            "page_size": str(page_size),
            "mature": "false",
        })
        req = urllib.request.Request(f"{self.API}?{params}",
                                     headers={"User-Agent": _USER_AGENT})
        # Anonymous Openverse access is rate-limited; a burst can transiently 401/429.
        # Retry a couple of times with backoff so one render doesn't lose its stills.
        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=25, context=_SSL_CONTEXT) as resp:
                    return json.load(resp).get("results", [])
            except urllib.error.HTTPError as exc:
                last_exc = exc
                if exc.code in (401, 429, 500, 502, 503) and attempt < 2:
                    time.sleep(2 * (attempt + 1))
                    continue
                raise
        raise last_exc  # pragma: no cover - loop always returns or raises above

    def fetch(self, subject: str, out_dir: str, limit: int = 12) -> list[str]:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        # over-fetch: many candidates get dropped for size/type before download
        candidates = self._search(subject, min(60, max(20, limit * 3)))

        saved: list[str] = []
        attributions: list[dict] = []
        for it in candidates:
            if len(saved) >= limit:
                break
            url = it.get("url") or ""
            title = it.get("title") or ""
            filetype = (it.get("filetype") or "").lower()
            width = it.get("width") or 0
            if not url or _SKIP_TITLE.search(title):
                continue
            if filetype not in ("jpg", "jpeg", "png") or width < 600:
                continue

            stem = re.sub(r"[^A-Za-z0-9.]+", "_", title or it.get("id", "ov"))[:76]
            ext = "png" if filetype == "png" else "jpg"
            dest = out / f"ov_{stem}.{ext}"
            try:
                req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
                with urllib.request.urlopen(req, timeout=30, context=_SSL_CONTEXT) as resp:
                    data = resp.read()
                if len(data) < 8000:      # too small to be a usable photo
                    continue
                dest.write_bytes(data)
            except Exception:  # noqa: BLE001 — one bad image shouldn't stop the batch
                continue

            saved.append(str(dest))
            lic = it.get("license", "")
            ver = it.get("license_version", "")
            attributions.append({
                "file": str(dest),
                "title": title or stem,
                "artist": it.get("creator") or "Unknown",
                "license": f"CC {lic.upper()} {ver}".strip(),
                "source_url": it.get("foreign_landing_url") or url,
            })

        merge_attributions(out_dir, attributions)
        return saved
