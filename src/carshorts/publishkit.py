"""Publish kit — everything the upload needs, generated per video.

  python -m carshorts.publishkit --script scripts/thar_deadpan.script.json \
      --spec specs_top5/mahindra-thar.json --provider groq

Writes out/<name>.publish.md: 3 title options (curiosity-gap, keyword-rich),
a description with specs, disclaimer, auto-collected credits (CC images,
press media, music), and hashtags. Facts come from the script/sheet only.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .adapters.footage import attribution_lines
from .adapters.llm import make_llm
from .models import Script, SpecSheet
from .produce import _apply_extras, _slug
from .stages.pipeline import _rows

SYSTEM = """You write YouTube Shorts metadata for a factually-strict car channel.
Given the SCRIPT, produce ONLY JSON:
{"titles": ["...", "...", "..."], "description_intro": "...", "hashtags": ["#...", ...]}
- 3 titles <70 chars: one curiosity-gap, one number-led, one search-keyword-led.
  Every title must contain the car name.
- description_intro: 2 punchy lines summarising the video, no invented facts.
- 8-12 hashtags: car name, brand, #Shorts, #CarShorts, India car tags."""


def build(script_path: str, spec_path: str | None, provider: str | None) -> str:
    script = Script.model_validate_json(Path(script_path).read_text())
    sheet = None
    if spec_path:
        sheet = SpecSheet.model_validate_json(Path(spec_path).read_text())
        _apply_extras(sheet)

    llm = make_llm(provider or "groq")
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
    credits = attribution_lines(f"assets/cars/{slug}/images")
    press = list(Path(f"assets/cars/{slug}/press").glob("*")) if Path(f"assets/cars/{slug}/press").exists() else []

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
    lines += ["", "## Hashtags", " ".join(data.get("hashtags", []))]

    out = Path("out") / f"{Path(script_path).stem.replace('.script','')}.publish.md"
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
