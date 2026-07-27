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
import os
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from pathlib import Path

try:
    import certifi

    _SSL_CONTEXT: ssl.SSLContext | None = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CONTEXT = None

# Wikimedia's User-Agent policy asks automated clients to identify themselves
# with a reachable contact; requests that do get throttled (429) far harder.
# Set CARSHORTS_CONTACT to an email or site URL in .env for the best rate limits.
_CONTACT = os.environ.get("CARSHORTS_CONTACT", "https://github.com/carsinshorts")
_USER_AGENT = f"carshorts/0.1 (automated CC car-footage fetcher; {_CONTACT})"
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


def _download(url: str, dest: Path) -> bool:
    """Fetch one image, backing off on Wikimedia's 429 rate-limit. Rapid
    sequential downloads get throttled after a handful; without this, a fetch
    silently kept only the first few images and starved the render of stills."""
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
            with urllib.request.urlopen(req, timeout=30, context=_SSL_CONTEXT) as resp:
                dest.write_bytes(resp.read())
            return True
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < 3:
                time.sleep(1.5 * (attempt + 1))
                continue
            return False
        except Exception:  # noqa: BLE001 — one bad image shouldn't stop the batch
            return False
    return False


class WikimediaImageSource(FootageSource):
    API = "https://en.wikipedia.org/w/api.php"
    COMMONS_API = "https://commons.wikimedia.org/w/api.php"

    def _get(self, api: str, params: dict) -> dict:
        url = f"{api}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(req, timeout=20, context=_SSL_CONTEXT) as resp:
            return json.load(resp)

    def _article_images(self, subject: str) -> list[dict]:
        """imageinfo dicts for images used on the subject's Wikipedia article."""
        data = self._get(self.API, {
            "action": "query", "titles": subject, "generator": "images",
            "gimlimit": "40", "prop": "imageinfo",
            "iiprop": "url|mime|size|extmetadata", "redirects": "1", "format": "json",
        })
        return self._extract_infos(data)

    def _commons_search(self, query: str) -> list[dict]:
        """imageinfo dicts for a File-namespace search on Wikimedia Commons.
        Used to find shots the article omits — notably interiors/dashboards."""
        data = self._get(self.COMMONS_API, {
            "action": "query", "generator": "search", "gsrsearch": query,
            "gsrnamespace": "6", "gsrlimit": "40", "prop": "imageinfo",
            "iiprop": "url|mime|size|extmetadata", "format": "json",
        })
        return self._extract_infos(data)

    @staticmethod
    def _extract_infos(data: dict) -> list[dict]:
        out = []
        for page in data.get("query", {}).get("pages", {}).values():
            info = (page.get("imageinfo") or [{}])[0]
            info["_title"] = page.get("title", "")
            out.append(info)
        return out

    def _candidates(self, subject: str) -> list[dict]:
        """Combine article images + several angle-specific Commons searches,
        deduped by URL. The extra angle queries (front/rear/side/interior) pull
        far more usable stills than a single search — enough to build a
        stills-first video and to survive the plate/wrong-vehicle vet."""
        combined = self._article_images(subject)
        for query in (f"{subject} interior", f"{subject} dashboard",
                      f"{subject} front", f"{subject} rear", f"{subject} side",
                      subject):
            combined += self._commons_search(query)
        seen, unique = set(), []
        for info in combined:
            url = info.get("url", "")
            if url and url not in seen:
                seen.add(url)
                unique.append(info)
        return unique

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
            if not _download(url, dest):
                continue
            time.sleep(0.3)   # polite pacing so Wikimedia doesn't 429 the batch

            saved.append(str(dest))
            attributions.append({
                "file": str(dest),
                "title": title,
                "artist": artist or "Unknown",
                "license": license_short,
                "source_url": info.get("descriptionurl", url),
            })

        merge_attributions(out_dir, attributions)
        return saved


def merge_attributions(out_dir: str, new_entries: list[dict]) -> None:
    """Append credit entries to attributions.json, de-duped by file path, so
    several sources (Wikimedia + Openverse) can fill one pool without clobbering
    each other's credits."""
    path = Path(out_dir) / "attributions.json"
    by_file: dict[str, dict] = {}
    if path.exists():
        for a in json.loads(path.read_text()):
            by_file[a["file"]] = a
    for e in new_entries:
        by_file[e["file"]] = e
    path.write_text(json.dumps(list(by_file.values()), indent=2))


def attribution_lines(out_dir: str) -> list[str]:
    """Read attributions.json and format credit lines for a video description."""
    path = Path(out_dir) / "attributions.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    return [f'{a["title"]} by {a["artist"]} ({a["license"]}) — {a["source_url"]}'
            for a in data]
