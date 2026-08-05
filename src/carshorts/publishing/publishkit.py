"""Publish kit — everything the upload needs, generated per video.

  python -m carshorts.publishing.publishkit --script data/scripts/thar_deadpan.script.json \
      --spec specs/mahindra-thar.json --provider groq

Writes out/<name>.publish.md: 3 title options (curiosity-gap, keyword-rich),
a description with specs, disclaimer, auto-collected credits (CC images,
press media, music), and hashtags. Facts come from the script/sheet only.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from carshorts.adapters.footage import attribution_lines
from carshorts.adapters.llm import make_llm
from carshorts.core import paths
from carshorts.core.models import Script, SpecSheet
from carshorts.rendering.produce import _apply_extras, _slug
from carshorts.writing.draft import _rows

SYSTEM = """You write YouTube Shorts metadata for a factually-strict car channel.
Given the SCRIPT, produce ONLY JSON:
{"titles": ["...", "...", "..."], "description_intro": "...", "hashtags": ["#...", ...]}
- 3 titles <70 chars: one curiosity-gap, one number-led, one search-keyword-led.
  Every title must contain the car name.
- description_intro: 2 punchy lines summarising the video, no invented facts.
- 8-12 hashtags: ONLY the car(s)/brand(s) ACTUALLY in this video, plus #Shorts,
  #CarShorts, generic India car tags. NEVER hashtag a brand not in the video."""

# Known Indian-market car brands — used to strip a brand hashtag that names a
# marque NOT in this video (the LLM once emitted #Kia on a Tata-vs-Hyundai clip,
# which shipped a wrong brand tag). Deterministic guard, independent of the model.
_CAR_BRANDS = {
    "tata", "hyundai", "maruti", "suzuki", "mahindra", "kia", "toyota", "honda",
    "renault", "nissan", "volkswagen", "skoda", "mg", "citroen", "jeep", "ford",
    "bmw", "mercedes", "audi", "byd", "force", "lexus", "volvo",
}


def _clean_hashtags(tags: list[str], subject: str, script_text: str) -> list[str]:
    """Drop brand hashtags for brands NOT in the video, and make sure every brand
    that IS in the subject has a tag. Model-independent so a stray #Kia can't ship."""
    hay = f"{subject} {script_text}".lower()
    out, seen = [], set()
    for t in tags:
        tag = t if t.startswith("#") else f"#{t}"
        low = tag.lstrip("#").lower()
        # a tag NAMES a brand if it equals one OR starts with one (compound tags
        # like 'HondaElevate', 'KiaSeltos') — drop it when that brand isn't here.
        brand = next((b for b in _CAR_BRANDS if low == b or low.startswith(b)), None)
        if brand and brand not in hay:
            continue
        if low not in seen:
            out.append(tag); seen.add(low)
    for brand in _CAR_BRANDS:              # ensure the video's OWN brands are tagged
        if brand in hay and not any(h.lstrip("#").lower().startswith(brand) for h in out):
            out.insert(0, f"#{brand.capitalize()}")
    return out


def build(script_path: str, spec_path: str | None, provider: str | None) -> str:
    script = Script.model_validate_json(Path(script_path).read_text())
    sheet = None
    if spec_path:
        sheet = SpecSheet.model_validate_json(Path(spec_path).read_text())
        _apply_extras(sheet)

    llm = make_llm(provider)  # None -> Gemini-first chain
    data_rows = llm.complete_json(SYSTEM, f"SCRIPT:\n{script.full_text}")
    data = data_rows[0] if isinstance(data_rows, list) and data_rows else data_rows

    # Promise check: a title may not promise anything the video doesn't deliver
    # (clickbait taxes trust). Titles that overpromise are dropped.
    titles = data.get("titles", [])
    if titles:
        try:
            verdict_rows = _rows(llm.complete_json(
                "You are a strict editor. For each TITLE, decide if it promises "
                "anything the SCRIPT does not actually deliver (facts, reveals, "
                "comparisons). Being punchy is fine; overpromising is not. "
                'Output ONLY JSON: [{"title": "...", "keep": true/false, "why": "..."}]',
                f"SCRIPT:\n{script.full_text}\n\nTITLES:\n" + "\n".join(titles)))
            kept = [r["title"] for r in verdict_rows if r.get("keep") and r.get("title")]
            dropped = [(r.get("title"), r.get("why")) for r in verdict_rows if not r.get("keep")]
            for t, why in dropped:
                print(f"  dropped title (overpromise): {t} — {why}")
            if kept:
                data["titles"] = kept
        except Exception:  # noqa: BLE001 — check is best-effort
            pass

    slug = _slug(script.subject)
    # credit ONLY the assets the FINAL actually uses (the folder may hold
    # hundreds of fetched files — crediting them all once produced a 37k-char
    # description; YouTube's hard cap is 5,000)
    credits = attribution_lines(str(paths.car_dir(slug) / "images"))
    used_assets: set[str] = set()
    for manifest in (paths.OUT / f"{slug}_final.manifest.json",
                     paths.OUT / f"{slug}_draft.manifest.json"):
        if manifest.exists():
            import json as _json
            m = _json.loads(manifest.read_text())
            used_assets = {c["asset"] for sec in m.get("sections", [])
                           for c in sec.get("cuts", [])}
            break
    if used_assets:
        def _used(line: str) -> bool:
            token = line.split(" by ")[0].replace("File:", "").strip()
            base = token.replace(" ", "_")
            return any(base[:40] in a or a.rsplit(".", 1)[0][:40] in line.replace(" ", "_")
                       for a in used_assets)
        credits = [c for c in credits if _used(c)]
    press_dir = paths.car_dir(slug) / "press"
    press = list(press_dir.glob("*")) if press_dir.exists() else []

    lines = [f"# Publish kit — {script.subject}", "", "## Title options"]
    lines += [f"{i+1}. {t}" for i, t in enumerate(data.get("titles", []))]
    lines += ["", "## Description", "", data.get("description_intro", ""), ""]
    if sheet:
        idx = sheet.fact_index()
        facts = [f"{s.value}" for n, s in idx.items()
                 if n in ("power", "torque", "engine_litre", "mileage", "price_estimate")]
        if facts:
            lines.append("⚙️ " + " • ".join(facts))
    lines += ["", "⚠️ Prices are estimates (source: CarDekho) — verify before buying.", ""]
    lines.append("Credits:")
    if press:
        lines.append("• Official images: Mahindra media kit (auto.mahindra.com/media-kit)"
                     if "mahindra" in slug else "• Official images: manufacturer media kit")
    for c in credits:
        lines.append(f"• {c}")
    lines.append("• B-roll: Pexels • Music: YouTube Audio Library • SFX: original")
    hashtags = _clean_hashtags(data.get("hashtags", []), script.subject, script.full_text)
    lines += ["", "## Hashtags", " ".join(hashtags)]

    out = paths.OUT / f"{Path(script_path).stem.replace('.script','')}.publish.md"
    out.write_text("\n".join(lines))
    print(f"publish kit -> {out}")
    return str(out)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--script", required=True)
    p.add_argument("--spec")
    p.add_argument("--provider", default=None)
    args = p.parse_args()
    build(args.script, args.spec, args.provider)


if __name__ == "__main__":
    main()
