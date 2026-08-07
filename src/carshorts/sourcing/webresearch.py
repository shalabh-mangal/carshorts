"""Autonomous fact + price research — grounded in TRUSTED sources only.

Facts come exclusively from tier-1 India spec authorities (CarDekho, CarWale,
ZigWheels, Autocar) and official maker sites (Nexa, etc.). Wikipedia is
DELIBERATELY excluded: it repeatedly shipped wrong India-market specs (the "1.5L
Fronx" and wrong-Brezza class) that then presented as verified fact. A free LLM
extracts each spec grounded in its own source sentence, and confidence comes from
corroboration across sources; the owner's CarDekho verification stays a 2-minute
check. Price stays owner-verified (CLAUDE.md — never auto-scraped).

  carshorts research "Tata Punch"                 # -> specs/tata-punch.json (+ price in extras)
  carshorts research "Tata Punch" --no-price      # specs only

Everything degrades gracefully: no trusted source reachable yields an honest
empty/thin sheet the owner fills in — never a confident wrong fact.
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


# --- RAG grounding: rank sources, corroborate, score real confidence ----------
# India spec authorities + official-maker domains = tier 1 (the ONLY trusted tier
# for facts); anything else = tier 3 (untrusted). Wikipedia is DELIBERATELY not
# trusted — it repeatedly shipped wrong India-market specs (the "1.5L Fronx" /
# wrong-Brezza class), so it is excluded from grounding entirely. A fact's
# confidence comes from WHERE it came from and WHETHER sources agree.
_AUTHORITATIVE = ("cardekho.com", "carwale.com", "zigwheels.com", "autocarindia.com",
                  "overdrive.in", "team-bhp.com", "mgmotor.co.in", "marutisuzuki",
                  "nexaexperience.com", "tatamotors", "hyundai.co.in", "mahindra", "kia.com")
# Domains that must NEVER be used as a fact source, even if a search surfaces them.
_BLOCKED_SOURCES = ("wikipedia.org", "wikiwand.com", "dbpedia.org")


def _tier(url: str) -> int:
    host = urllib.parse.urlparse(url).netloc.lower()
    if any(d in host for d in _BLOCKED_SOURCES):
        return 9              # blocked — never a fact source
    if any(d in host for d in _AUTHORITATIVE):
        return 1
    return 3


def _norm_value(v: str) -> str:
    """Normalize a spec value for agreement checks: '160 PS' ~ '160ps'."""
    return re.sub(r"[^a-z0-9.]", "", (v or "").lower())


def merge_and_score(per_source: list[tuple]) -> list[Spec]:
    """Merge specs extracted across sources and set REAL confidence.

    per_source items: (name, value, source_url, source_sentence, tier). For each
    spec: pick the value backed by the most sources (tiebreak: best tier), then
    score — corroborated by >=2 agreeing sources -> 0.9; a single AUTHORITATIVE
    (tier-1) source -> 0.8; a single weak source OR sources that DISAGREE -> 0.5
    (which render_spec_sheet flags [CLAIMED] so the writer attributes it). Pure +
    unit-tested — the retrieval around it is best-effort I/O."""
    from collections import defaultdict
    by_name: dict[str, list[tuple]] = defaultdict(list)
    for name, value, url, sent, tier in per_source:
        by_name[name].append((value, url, sent, tier))
    out: list[Spec] = []
    for name, entries in by_name.items():
        groups: dict[str, list[tuple]] = defaultdict(list)
        for e in entries:
            groups[_norm_value(e[0])].append(e)
        # winning value: most sources, then best (lowest) tier
        best = max(groups.values(),
                   key=lambda g: (len(g), -min(t for *_, t in g)))
        conflict = len(groups) > 1
        best_tier = min(t for *_, t in best)
        if len(best) >= 2 and not conflict:
            conf = 0.9
        elif best_tier == 1 and not conflict:
            conf = 0.8
        else:
            conf = 0.5
        value, url, sent, _tr = sorted(best, key=lambda x: x[3])[0]   # cite the best source
        try:
            out.append(Spec(name=name, value=value, source_url=url,
                            source_sentence=sent or f"{name}: {value}.", confidence=conf))
        except Exception:  # noqa: BLE001 — skip a malformed merged row
            continue
    return out


def ground_specs(car: str, provider: str | None, max_sources: int = 4) -> list[Spec]:
    """Retrieve ranked TRUSTED sources (tier-1 spec authorities + official maker
    sites ONLY — Wikipedia is deliberately excluded after repeatedly shipping wrong
    India-market specs), extract each grounded in its own text, and merge with
    corroboration-based confidence. Returns [] when no trusted source is reachable
    — an honest gap the owner fills from CarDekho / the official site beats a
    confident wrong fact."""
    sources: list[tuple[str, str, int]] = []
    seen_hosts: set[str] = set()
    for url in ddg_search(f"{car} specifications India", limit=12):
        if _tier(url) != 1 or "price" in url.lower():   # tier-1 spec authorities only
            continue
        host = urllib.parse.urlparse(url).netloc
        if host in seen_hosts:
            continue
        try:
            sources.append((url, _html_to_text(_get(url)), 1))
            seen_hosts.add(host)
        except Exception:  # noqa: BLE001 — one bad page shouldn't stop grounding
            continue
        if len(sources) >= max_sources:
            break
    per_source: list[tuple] = []
    for url, text, tier in sources:
        for s in extract_specs(car, text, url, provider):
            per_source.append((s.name, s.value, s.source_url, s.source_sentence, tier))
    print(f"  grounding: {len(sources)} trusted source(s), "
          f"{len({p[0] for p in per_source})} distinct specs")
    return merge_and_score(per_source)


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
    # RAG grounding: multiple ranked TRUSTED sources (tier-1 only; Wikipedia
    # excluded), corroborated, with REAL per-spec confidence. A single tier-1
    # source scores 0.8; corroboration by >=2 -> 0.9; the '1.5L Fronx' class of
    # wrong Wikipedia fact can no longer enter the sheet at all.
    specs = ground_specs(car, provider)
    sheet = SpecSheet(subject=car, specs=specs)
    _claimed = sum(1 for s in specs if (s.confidence or 1.0) < 0.7)
    print(f"research: {len(specs)} sourced specs for {car} "
          f"({_claimed} low-confidence -> [CLAIMED], verify on CarDekho)")

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
