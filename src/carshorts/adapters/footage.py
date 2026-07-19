"""The FootageSource adapter — where legal, free car visuals come from.

Free + monetization-safe: Wikimedia Commons. Its images are CC-licensed or
public-domain (reuse allowed WITH attribution) — unlike scraped footage from
other channels, which is copyright infringement and blocks YouTube monetization.
This is the "stills" backbone of the visuals strategy; the renderer animates
them with a slow zoom so they feel like video.

Two guarantees enforced here, mirroring the accuracy design:
  1. LICENSE — an image is downloaded only if its Commons metadata says it is
     free (CC / public domain). Non-free / "fair use" files are skipped.
  2. ATTRIBUTION — every downloaded image records its author, license, and URL
     to attributions.json, so the video description can credit it (required by
     CC-BY). No attribution captured -> not used.

No AI is involved: we never invent an image or a credit.
"""
from __future__ import annotations

import json
import re
import ssl
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from pathlib import Path

try:
    import certifi

    _SSL_CONTEXT: ssl.SSLContext | None = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CONTEXT = None

_USER_AGENT = "carshorts/0.1 (car-shorts factory; educational use)"
# Skip files that are almost never usable car footage.
_SKIP_TITLE = re.compile(r"logo|icon|map|flag|diagram|\.svg$|seal|emblem", re.I)


class FootageSource(ABC):
    @abstractmethod
    def fetch(self, subject: str, out_dir: str, limit: int = 5) -> list[str]:
        """Download up to `limit` usable images for `subject`; return their paths."""


def _looks_free(license_short: str) -> bool:
    text = (license_short or "").lower()
    if "fair use" in text or "non-free" in text:
        return False
    return "cc" in text or "public domain" in text or "cc0" in text


class WikimediaImageSource(FootageSource):
    API = "https://en.wikipedia.org/w/api.php"

    def _get(self, params: dict) -> dict:
        url = f"{self.API}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(req, timeout=20, context=_SSL_CONTEXT) as resp:
            return json.load(resp)

    def _candidates(self, subject: str) -> list[dict]:
        """Return imageinfo dicts for images used on the subject's article."""
        data = self._get({
            "action": "query",
            "titles": subject,
            "generator": "images",
            "gimlimit": "40",
            "prop": "imageinfo",
            "iiprop": "url|mime|size|extmetadata",
            "redirects": "1",
            "format": "json",
        })
        pages = data.get("query", {}).get("pages", {})
        out = []
        for page in pages.values():
            info = (page.get("imageinfo") or [{}])[0]
            info["_title"] = page.get("title", "")
            out.append(info)
        return out

    def fetch(self, subject: str, out_dir: str, limit: int = 5) -> list[str]:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        attributions: list[dict] = []
        saved: list[str] = []

        for info in self._candidates(subject):
            if len(saved) >= limit:
                break
            title = info.get("_title", "")
            url = info.get("url", "")
            mime = info.get("mime", "")
            width = info.get("width", 0)
            if not url or _SKIP_TITLE.search(title):
                continue
            if mime not in ("image/jpeg", "image/png") or width < 600:
                continue

            meta = info.get("extmetadata", {})
            license_short = meta.get("LicenseShortName", {}).get("value", "")
            if not _looks_free(license_short):
                continue
            artist = re.sub(r"<[^>]+>", "", meta.get("Artist", {}).get("value", "")).strip()

            fname = re.sub(r"[^A-Za-z0-9.]+", "_", title.replace("File:", ""))[:80]
            dest = out / fname
            try:
                req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
                with urllib.request.urlopen(req, timeout=30, context=_SSL_CONTEXT) as resp:
                    dest.write_bytes(resp.read())
            except Exception:  # noqa: BLE001 — one bad image shouldn't stop the batch
                continue

            saved.append(str(dest))
            attributions.append({
                "file": str(dest),
                "title": title,
                "artist": artist or "Unknown",
                "license": license_short,
                "source_url": info.get("descriptionurl", url),
            })

        (out / "attributions.json").write_text(json.dumps(attributions, indent=2))
        return saved


def attribution_lines(out_dir: str) -> list[str]:
    """Read attributions.json and format credit lines for a video description."""
    path = Path(out_dir) / "attributions.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    return [f'{a["title"]} by {a["artist"]} ({a["license"]}) — {a["source_url"]}'
            for a in data]
