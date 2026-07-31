"""News crawler — fresh, source-bound car news for specs_extras.

  python -m carshorts.sourcing.newscrawl "Mahindra Thar"            # preview what it found
  python -m carshorts.sourcing.newscrawl "Tata Punch" --write       # merge into specs_extras/
  python -m carshorts.sourcing.newscrawl "Hyundai Creta" --days 30

WHY: news is the strongest hook a car Short can have ("X just happened" beats
"X exists"), and until now every news item was HAND-curated into
specs_extras/<slug>.json. That human step is what structurally blocked a daily
cadence — the heartbeat has nothing to draft when extras are missing.

WHAT IT WILL NOT DO (deliberate, see CLAUDE.md non-negotiables):
  - It never writes price fields. "Prices are estimates from a one-off
    CarDekho/CarWale lookup — never automated scraping of them." If a car has no
    price yet, this tool SAYS SO and leaves the field for the owner. A fabricated
    or scraped price would poison the number-guard's whole premise.
  - It reads RSS/Atom feeds only — formats published FOR syndication — and never
    scrapes article bodies. robots.txt is consulted before every host.

Each item keeps the outlet's own wording (including hedges like "spied" or
"expected") plus its URL and date, so the number-guard and the fact-check
skeptic still gate every claim downstream. This tool gathers evidence; it does
not decide what is true.

Sources are DATA, not code: edit data/news_sources.json to curate them.
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
import xml.etree.ElementTree as ET
from pathlib import Path

from carshorts.core import paths

try:
    import certifi

    _SSL: ssl.SSLContext | None = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL = None

_UA = "carshorts/0.1 (car-shorts factory; RSS reader; contact: repo owner)"
SOURCES_FILE = paths.NEWS_SOURCES
EXTRAS_DIR = Path("specs_extras")

# Indian car-news outlets that publish RSS. Overridable via data/news_sources.json
# so the owner curates sources without touching code.
DEFAULT_SOURCES = [
    {"name": "Autocar India", "url": "https://www.autocarindia.com/rss/news"},
    {"name": "RushLane", "url": "https://www.rushlane.com/feed"},
    {"name": "ZigWheels", "url": "https://www.zigwheels.com/rss/news"},
    {"name": "ET Auto", "url": "https://auto.economictimes.indiatimes.com/rss/topstories"},
    {"name": "Autocar Professional", "url": "https://www.autocarpro.in/rss"},
]

_robots_cache: dict[str, urllib.robotparser.RobotFileParser | None] = {}


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def load_sources() -> list[dict]:
    if SOURCES_FILE.exists():
        try:
            data = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
            feeds = data.get("feeds") if isinstance(data, dict) else data
            if feeds:
                return list(feeds)
        except Exception:  # noqa: BLE001 — a bad source file must not stop the crawl
            pass
    return list(DEFAULT_SOURCES)


def _robots_allows(url: str) -> bool:
    """Consult robots.txt before fetching. Unreachable robots => allowed
    (standard practice), unparseable => allowed, explicit disallow => skip."""
    parts = urllib.parse.urlparse(url)
    host = f"{parts.scheme}://{parts.netloc}"
    if host not in _robots_cache:
        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(f"{host}/robots.txt")
        try:
            req = urllib.request.Request(f"{host}/robots.txt", headers={"User-Agent": _UA})
            with urllib.request.urlopen(req, timeout=10, context=_SSL) as resp:
                rp.parse(resp.read().decode("utf-8", "replace").splitlines())
            _robots_cache[host] = rp
        except Exception:  # noqa: BLE001 — no robots.txt reachable = no prohibition
            _robots_cache[host] = None
    rp = _robots_cache[host]
    return True if rp is None else rp.can_fetch(_UA, url)


def _fetch(url: str, timeout: int = 20) -> bytes | None:
    if not _robots_allows(url):
        print(f"     [robots] skipping {url}")
        return None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL) as resp:
            return resp.read()
    except Exception as exc:  # noqa: BLE001 — one dead feed must not stop the rest
        print(f"     [warn] {urllib.parse.urlparse(url).netloc}: {str(exc)[:70]}")
        return None


def _text(node) -> str:
    return re.sub(r"<[^>]+>", "", (node.text or "")).strip() if node is not None else ""


def _parse_date(raw: str) -> datetime.datetime | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(raw)
        return dt.replace(tzinfo=None) if dt else None
    except Exception:  # noqa: BLE001
        pass
    try:
        return datetime.datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def parse_feed(payload: bytes, source_name: str) -> list[dict]:
    """Parse RSS 2.0 or Atom into {title, link, summary, published, source}."""
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        return []
    items: list[dict] = []
    # RSS: channel/item ; Atom: {ns}entry
    nodes = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
    def find(node, *names):
        for n in names:
            got = node.find(n)
            if got is not None:
                return got
        return None

    for node in nodes:
        title = _text(find(node, "title", "{http://www.w3.org/2005/Atom}title"))
        link_node = find(node, "link", "{http://www.w3.org/2005/Atom}link")
        link = _text(link_node) or (link_node.get("href") if link_node is not None else "")
        summary = _text(find(node, "description", "{http://www.w3.org/2005/Atom}summary"))
        pub = _text(find(node, "pubDate", "{http://www.w3.org/2005/Atom}updated",
                         "{http://www.w3.org/2005/Atom}published"))
        if title and link:
            items.append({"title": title, "link": link, "summary": summary[:400],
                          "published": _parse_date(pub), "source": source_name})
    return items


def _car_tokens(car: str, slug: str) -> set[str]:
    """Distinctive name tokens for matching. Brand-only words are too broad to
    match on alone (every Maruti story would match the Swift)."""
    tokens = {t for t in slug.split("-") if len(t) >= 3}
    generic = {"maruti", "suzuki", "tata", "mahindra", "hyundai", "kia", "toyota", "motors"}
    model = tokens - generic
    return model or tokens


def matches_car(item: dict, tokens: set[str], aliases: set[str]) -> bool:
    haystack = f"{item['title']} {item['summary']}".lower()
    return any(t in haystack for t in (tokens | aliases))


def gather(car: str, days: int = 45, limit: int = 8) -> list[dict]:
    slug = _slug(car)
    tokens = _car_tokens(car, slug)
    aliases: set[str] = set()
    extras_path = EXTRAS_DIR / f"{slug}.json"
    if extras_path.exists():
        try:
            aliases = {a.lower() for a in
                       json.loads(extras_path.read_text(encoding="utf-8")).get("aliases", [])}
        except Exception:  # noqa: BLE001
            pass

    cutoff = datetime.datetime.now() - datetime.timedelta(days=days)
    found: list[dict] = []
    seen_links: set[str] = set()
    seen_titles: set[str] = set()

    print(f"  matching on: {sorted(tokens | aliases)}")
    for src in load_sources():
        payload = _fetch(src["url"])
        if not payload:
            continue
        items = parse_feed(payload, src["name"])
        hits = 0
        for item in items:
            if not matches_car(item, tokens, aliases):
                continue
            if item["published"] and item["published"] < cutoff:
                continue
            key = re.sub(r"[^a-z0-9]+", "", item["title"].lower())[:60]
            if item["link"] in seen_links or key in seen_titles:
                continue
            seen_links.add(item["link"])
            seen_titles.add(key)
            found.append(item)
            hits += 1
        print(f"     {src['name']:<22} {len(items):>3} items, {hits} match")

    found.sort(key=lambda i: i["published"] or datetime.datetime.min, reverse=True)
    return found[:limit]


def to_news_entries(items: list[dict]) -> list[dict]:
    """Shape matches specs_extras `news`: produce._apply_extras turns each into a
    SOURCED spec, so the wording must stay the outlet's own (hedges included)."""
    out = []
    for item in items:
        when = item["published"].strftime("%B %Y") if item["published"] else "recently"
        out.append({"fact": item["title"].strip(), "source": item["link"], "date": when})
    return out


def merge_into_extras(slug: str, news: list[dict], write: bool = False) -> dict:
    """Merge news into specs_extras/<slug>.json WITHOUT touching price fields."""
    path = EXTRAS_DIR / f"{slug}.json"
    extras = {}
    if path.exists():
        extras = json.loads(path.read_text(encoding="utf-8"))

    existing = {n.get("source") for n in extras.get("news", [])}
    fresh = [n for n in news if n["source"] not in existing]
    extras["news"] = (extras.get("news", []) + fresh)[:8]

    if write:
        EXTRAS_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(extras, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"added": len(fresh), "total_news": len(extras["news"]),
            "has_price": bool(extras.get("price_estimate")), "path": str(path)}


def main() -> None:
    ap = argparse.ArgumentParser(description="Crawl fresh car news into specs_extras.")
    ap.add_argument("car", help='Car name, e.g. "Tata Punch".')
    ap.add_argument("--days", type=int, default=45, help="Freshness window (default 45).")
    ap.add_argument("--limit", type=int, default=8, help="Max news items to keep.")
    ap.add_argument("--write", action="store_true",
                    help="Merge into specs_extras/<slug>.json (default: preview only).")
    args = ap.parse_args()

    slug = _slug(args.car)
    print(f"news crawl — {args.car}  (last {args.days} days)")
    items = gather(args.car, days=args.days, limit=args.limit)
    if not items:
        print("\n  no matching stories found — try --days 90, or add feeds to "
              "data/news_sources.json")
        return

    news = to_news_entries(items)
    print(f"\n  {len(news)} story(ies):")
    for n in news:
        print(f"   - [{n['date']}] {n['fact'][:88]}")
        print(f"     {n['source'][:100]}")

    result = merge_into_extras(slug, news, write=args.write)
    if args.write:
        print(f"\n  merged {result['added']} new item(s) -> {result['path']} "
              f"({result['total_news']} total)")
    else:
        print(f"\n  preview only — re-run with --write to merge into {result['path']}")

    if not result["has_price"]:
        print("\n  ⚠ NO PRICE in this extras file. This tool will not scrape or invent "
              "one (CLAUDE.md rule).\n    Add price_estimate / value_variant / "
              "value_features by hand from a CarDekho/CarWale lookup\n    before this car "
              "can carry a 'value' beat.")


if __name__ == "__main__":
    main()
