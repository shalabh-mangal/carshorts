"""Autonomous fact + price research — the replacement for the thin Wikipedia crawl.

The old `crawl` only read Wikipedia's structured infobox and under-delivered
(Tata Punch came back with 2 specs, one of them the EV's battery mis-read as
"power"). This module instead pulls the FULL article text and lets a free LLM
(GROQ) extract a rich, sourced spec sheet — every fact carries the exact sentence
it came from, so the owner's CarDekho verification stays a 2-minute check, not a
re-research. Price + fresh-model facts come from a best-effort web search, since
they aren't on Wikipedia (prices stay owner-verified — CLAUDE.md).

  carshorts research "Tata Punch"                 # -> specs/tata-punch.json (+ price in extras)
  carshorts research "Tata Punch" --no-price      # specs only

Everything degrades gracefully: no search, no LLM, or a bad page never crashes a
run — it just yields fewer sourced facts and reports the gap.
"""
from __future__ import annotations

import argparse
import json
import re
import urllib.parse
import urllib.request

from carshorts.adapters.llm import make_llm
from carshorts.core import paths
from carshorts.core.models import Spec, SpecSheet

_UA = {"User-Agent": "carshorts/0.1 (research; contact via .env CARSHORTS_CONTACT)"}


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _get(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "ignore")


def _html_to_text(html: str) -> str:
    html = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    text = re.sub(r"&[a-z#0-9]+;", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def wikipedia_text(subject: str) -> tuple[str, str]:
    """Full plain-text extract of the best-matching Wikipedia article, plus its
    canonical URL. Returns ("", "") if nothing is found."""
    api = "https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode({
        "action": "query", "list": "search", "srsearch": subject,
        "format": "json", "srlimit": "1"})
    try:
        hits = json.loads(_get(api)).get("query", {}).get("search", [])
        if not hits:
            return "", ""
        title = hits[0]["title"]
        ext = "https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode({
            "action": "query", "prop": "extracts", "explaintext": "1",
            "titles": title, "format": "json", "redirects": "1"})
        pages = json.loads(_get(ext)).get("query", {}).get("pages", {})
        page = next(iter(pages.values()), {})
        url = "https://en.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"))
        return page.get("extract", ""), url
    except Exception:  # noqa: BLE001 — no article just means fewer facts
        return "", ""


_SPEC_SYSTEM = (
    "You extract VERIFIABLE car specifications from an article about the "
    "India-market model. Output ONLY a JSON array; each item: "
    '{"name": "<short key: power/torque/engine/mileage/boot_space/'
    'ground_clearance/wheelbase/safety_rating/transmission/body_type/length>", '
    '"value": "<value WITH its unit, e.g. 86 bhp, 366 litres, 5-star>", '
    '"source_sentence": "<the exact sentence from the article stating it>"}. '
    "Rules: include a fact ONLY if the article explicitly states it; copy the "
    "source sentence verbatim; keep units; prefer the current petrol model; do "
    "NOT invent, estimate, or include a price. Max 12 items, strongest first."
)


def extract_specs(car: str, text: str, source_url: str, provider: str | None) -> list[Spec]:
    if not text:
        return []
    try:
        from carshorts.writing.draft import _rows
        rows = _rows(make_llm(provider).complete_json(
            _SPEC_SYSTEM, f"CAR: {car}\n\nARTICLE:\n{text[:12000]}"))
    except Exception:  # noqa: BLE001 — no LLM just means no extraction
        return []
    specs: list[Spec] = []
    seen: set[str] = set()
    for row in rows:
        name = str(row.get("name", "")).strip().lower().replace(" ", "_")
        value = str(row.get("value", "")).strip()
        sentence = str(row.get("source_sentence", "")).strip()
        if not name or not value or name in seen or len(value) > 60:
            continue
        seen.add(name)
        try:
            specs.append(Spec(name=name, value=value, source_url=source_url,
                              source_sentence=sentence or f"{car}: {value}.", confidence=0.85))
        except Exception:  # noqa: BLE001 — a malformed row is skipped, not fatal
            continue
    return specs


def ddg_search(query: str, limit: int = 5) -> list[str]:
    """Best-effort free web search (DuckDuckGo HTML). Returns result URLs, or []
    if it's blocked/unavailable — callers must not depend on it."""
    try:
        html = _get("https://html.duckduckgo.com/html/?" +
                    urllib.parse.urlencode({"q": query}))
    except Exception:  # noqa: BLE001
        return []
    urls: list[str] = []
    for m in re.finditer(r'uddg=([^"&]+)', html):
        try:
            url = urllib.parse.unquote(m.group(1))
        except Exception:  # noqa: BLE001
            continue
        if url.startswith("http") and url not in urls:
            urls.append(url)
        if len(urls) >= limit:
            break
    return urls


_PRICE_SYSTEM = (
    "Extract the current India price of the car from this page. Output ONLY "
    'JSON: {"price": "<e.g. ₹6 lakh onwards, or ₹6–10 lakh>" or null, '
    '"source_sentence": "<verbatim sentence>"}. Only if explicitly stated; do not estimate.'
)


def research_price(car: str, provider: str | None) -> dict:
    """Best-effort sourced price. Owner still verifies (CLAUDE.md: prices manual)."""
    for url in ddg_search(f"{car} price ex-showroom India specifications", limit=4):
        try:
            text = _html_to_text(_get(url))
            data = make_llm(provider).complete_json(
                _PRICE_SYSTEM, f"CAR: {car}\n\nPAGE:\n{text[:8000]}")
            price = (data or {}).get("price")
            if price:
                return {"price_estimate": str(price)[:40], "price_source": url,
                        "price_note": "web-sourced; verify on CarDekho, on-road varies by city"}
        except Exception:  # noqa: BLE001 — try the next result
            continue
    return {}


def research(car: str, provider: str | None = None, want_price: bool = True) -> SpecSheet:
    slug = _slug(car)
    text, url = wikipedia_text(car)
    specs = extract_specs(car, text, url or f"https://en.wikipedia.org/wiki/{slug}", provider)
    sheet = SpecSheet(subject=car, specs=specs)
    print(f"research: {len(specs)} sourced specs for {car}"
          + (f" (from {url})" if url else " (no Wikipedia article found)"))

    out = paths.SPECS / f"{slug}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(sheet.model_dump_json(indent=2), encoding="utf-8")
    print(f"  wrote {out}")

    if want_price:
        price = research_price(car, provider)
        ex_path = paths.SPECS_EXTRAS / f"{slug}.json"
        extras = {}
        if ex_path.exists():
            try:
                extras = json.loads(ex_path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                extras = {}
        extras.setdefault("aliases", [t for t in slug.split("-") if len(t) >= 3])
        if price:
            extras.update(price)
            print(f"  price: {price['price_estimate']}  (verify on CarDekho)")
        else:
            print("  price: not found on the web — add it by hand (CarDekho lookup)")
        ex_path.parent.mkdir(parents=True, exist_ok=True)
        ex_path.write_text(json.dumps(extras, indent=2, ensure_ascii=False), encoding="utf-8")
    return sheet


def main() -> None:
    ap = argparse.ArgumentParser(description="Autonomous web fact + price research into spec sheets.")
    ap.add_argument("car", help='Car name, e.g. "Tata Punch".')
    ap.add_argument("--provider", choices=["deepseek", "gemini", "groq", "cerebras", "openrouter", "ollama"],
                    help="LLM backend for extraction (or CARSHORTS_LLM). Default gemini.")
    ap.add_argument("--no-price", action="store_true", help="Skip the web price search.")
    args = ap.parse_args()
    research(args.car, provider=args.provider, want_price=not args.no_price)


if __name__ == "__main__":
    main()
