"""Stock-video source — real moving b-roll, free and licensed.

Pexels' library is free to use (no attribution required by their license) and
has a free API. It does NOT have footage of a *specific* model, so this supplies
GENERIC car motion — driving, dashboards, interiors, steering wheels — which the
producer intercuts with the exact-car stills (which carry the model's identity).
Motion from stock + identity from stills = a video that feels shot, for free.

Needs a free key in PEXELS_API_KEY (get one at pexels.com/api).
"""
from __future__ import annotations

import json
import os
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

_UA = "carshorts/0.1"
# Brand-NEUTRAL detail / POV shots only. Full-car or badge/logo shots (steering
# wheel horns, exterior driving) would show a RIVAL brand — the exact car's
# identity must come from the stills, never from generic stock. These detail
# shots (gauges, vents, road POV) rarely reveal a badge.
_DEFAULT_QUERIES = (
    "car speedometer closeup", "car gear shifter", "driving pov road",
    "car dashboard vents", "car seats interior", "tachometer closeup",
)


class StockVideoSource(ABC):
    @abstractmethod
    def fetch(self, out_dir: str, limit: int = 5, queries=None) -> list[str]:
        """Download up to `limit` short generic clips; return their paths."""


class PexelsVideoSource(StockVideoSource):
    SEARCH = "https://api.pexels.com/videos/search"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("PEXELS_API_KEY")

    def _search(self, query: str, per_page: int) -> list[dict]:
        params = urllib.parse.urlencode({
            "query": query, "per_page": per_page, "orientation": "portrait",
        })
        req = urllib.request.Request(
            f"{self.SEARCH}?{params}",
            headers={"Authorization": self.api_key or "", "User-Agent": _UA},
        )
        with urllib.request.urlopen(req, timeout=25, context=_SSL_CONTEXT) as resp:
            return json.load(resp).get("videos", [])

    @staticmethod
    def _best_file(video: dict) -> str | None:
        """Pick a portrait-ish file that isn't huge (<= 1920 tall), else any."""
        files = sorted(video.get("video_files", []),
                       key=lambda f: (f.get("height") or 0), reverse=True)
        for f in files:
            h, w = f.get("height") or 0, f.get("width") or 0
            if f.get("link") and h >= w and h <= 2200:
                return f["link"]
        return files[0]["link"] if files and files[0].get("link") else None

    def fetch(self, out_dir: str, limit: int = 5, queries=None) -> list[str]:
        if not self.api_key:
            raise RuntimeError("PEXELS_API_KEY not set — get a free key at pexels.com/api")
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        queries = list(queries or _DEFAULT_QUERIES)
        saved: list[str] = []

        per_query = max(1, limit // len(queries) + 1)
        for query in queries:
            if len(saved) >= limit:
                break
            try:
                videos = self._search(query, per_query)
            except Exception:  # noqa: BLE001 — one failed query shouldn't stop the rest
                continue
            for video in videos:
                if len(saved) >= limit:
                    break
                link = self._best_file(video)
                if not link:
                    continue
                dest = out / f"{query.replace(' ', '_')}_{video.get('id', 'x')}.mp4"
                try:
                    req = urllib.request.Request(link, headers={"User-Agent": _UA})
                    with urllib.request.urlopen(req, timeout=60, context=_SSL_CONTEXT) as resp:
                        dest.write_bytes(resp.read())
                except Exception:  # noqa: BLE001
                    continue
                saved.append(str(dest))
        return saved


class PixabayVideoSource(StockVideoSource):
    """Second free, monetization-safe stock-video source (Pixabay Content License —
    free commercial use, no attribution required). Same role as Pexels: GENERIC
    brand-neutral detail/POV motion only, never a full car (that would show a rival
    badge — identity comes from the exact-car stills). Having two sources means one
    key being unset or one library being thin no longer starves the render.

    Needs a free key in PIXABAY_API_KEY (get one at pixabay.com/api/docs).
    """
    SEARCH = "https://pixabay.com/api/videos/"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("PIXABAY_API_KEY")

    def _search(self, query: str, per_page: int) -> list[dict]:
        params = urllib.parse.urlencode({
            "key": self.api_key or "", "q": query, "per_page": max(3, per_page),
            "video_type": "film", "safesearch": "true",
        })
        req = urllib.request.Request(f"{self.SEARCH}?{params}",
                                     headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=25, context=_SSL_CONTEXT) as resp:
            return json.load(resp).get("hits", [])

    @staticmethod
    def _best_file(hit: dict) -> str | None:
        """Prefer a portrait-ish rendition that isn't huge; Pixabay ships fixed
        sizes (large/medium/small/tiny) each with width/height."""
        files = [v for v in (hit.get("videos") or {}).values() if v.get("url")]
        portrait = sorted((f for f in files if (f.get("height") or 0) >= (f.get("width") or 0)
                           and (f.get("height") or 0) <= 2200),
                          key=lambda f: f.get("height") or 0, reverse=True)
        pick = (portrait or files)
        return pick[0]["url"] if pick else None

    def fetch(self, out_dir: str, limit: int = 5, queries=None) -> list[str]:
        if not self.api_key:
            raise RuntimeError("PIXABAY_API_KEY not set — get a free key at pixabay.com/api/docs")
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        queries = list(queries or _DEFAULT_QUERIES)
        saved: list[str] = []
        per_query = max(1, limit // len(queries) + 1)
        for query in queries:
            if len(saved) >= limit:
                break
            try:
                hits = self._search(query, per_query)
            except Exception:  # noqa: BLE001 — one failed query shouldn't stop the rest
                continue
            for hit in hits:
                if len(saved) >= limit:
                    break
                link = self._best_file(hit)
                if not link:
                    continue
                dest = out / f"pixabay_{query.replace(' ', '_')}_{hit.get('id', 'x')}.mp4"
                try:
                    req = urllib.request.Request(link, headers={"User-Agent": _UA})
                    with urllib.request.urlopen(req, timeout=60, context=_SSL_CONTEXT) as resp:
                        dest.write_bytes(resp.read())
                except Exception:  # noqa: BLE001
                    continue
                saved.append(str(dest))
        return saved


def build_video_source() -> StockVideoSource | None:
    """Pick the configured stock-video source. Prefer Pexels (mature key in use),
    fall back to Pixabay, else None (no key -> the render simply runs stills-only,
    which `_stock_default` already handles). Two sources = resilience, not spend:
    both are free and require no attribution."""
    if os.environ.get("PEXELS_API_KEY"):
        return PexelsVideoSource()
    if os.environ.get("PIXABAY_API_KEY"):
        return PixabayVideoSource()
    return None
