"""Premium script studio: spec sheet -> best fact-checked script.

  python -m carshorts.writescript --spec specs_top5/tata-nexon.json \
      --persona bhai --language hinglish --variants 3 --provider groq \
      --out scripts/nexon_bhai.script.json

Pipeline (script-first — perfect the words before spending render compute):
  1. VARIANTS  — draft N scripts, each from a different opening angle + persona.
  2. JUDGE     — a ruthless editor scores them and picks the best.
  3. EDITOR    — punch up the winner (sharper hook, tighter pacing, better CTA)
                 without adding any unsourced fact.
  4. SAFETY    — structural + number-guard + LLM fact-check; print Gate 1 report.

Output is a .script.json — render it later, free, with:
  python -m carshorts.produce --script-file <that file> --spec <spec> --stock
"""
from __future__ import annotations

import argparse
from pathlib import Path

from .adapters.llm import make_llm
from .gate1 import render_gate1_report
from .models import SpecSheet
from .produce import _apply_extras, _slug
from .prompts.templates import ANGLES, FORMATS
from .stages.pipeline import (
    draft_script,
    fact_check,
    judge_scripts,
    punch_up_script,
    structural_citation_check,
    unsourced_numbers_check,
)


def write_premium(spec_path: str, out_path: str, persona: str = "", language: str = "english",
                  variants: int = 3, provider: str | None = None,
                  video_format: str = "spotlight") -> str:
    sheet = SpecSheet.model_validate_json(Path(spec_path).read_text())
    guidance = _apply_extras(sheet)          # sourced price + value-pick, if any
    from .learnings import load_learnings_guidance
    craft = load_learnings_guidance()
    if craft:
        guidance = f"{guidance}\n\n{craft}" if guidance else craft
    fmt = FORMATS.get(video_format, "")
    if fmt:
        guidance = f"{guidance}\n\n{fmt}" if guidance else fmt
    llm = make_llm(provider)

    print(f"1/4  drafting {variants} variant(s) [persona={persona or 'default'}, {language}]...")
    candidates = []
    for i in range(variants):
        angle = ANGLES[i % len(ANGLES)]
        candidates.append(draft_script(sheet, llm, language=language, guidance=guidance,
                                       persona=persona, angle=angle))

    print("2/4  judging...")
    best_index, why = judge_scripts(candidates, llm)
    best = candidates[best_index]
    print(f"     picked variant {best_index} — {why}")

    print("3/4  punch-up editor pass...")
    final = best
    try:
        final = punch_up_script(best, sheet, llm)
    except Exception as exc:  # noqa: BLE001 — keep the judged best if the editor hiccups
        print(f"     editor pass failed ({exc}); keeping the judged best.")

    # Save NOW so a later fact-check hiccup can never lose the script.
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(final.model_dump_json(indent=2))

    print("4/4  safety (structural + number-guard + fact-check)...")
    structural = structural_citation_check(final, sheet)
    numbers = unsourced_numbers_check(final, sheet)
    try:
        report = fact_check(final, sheet, llm)
        print("\n" + render_gate1_report(final, sheet, report, structural + numbers) + "\n")
    except Exception as exc:  # noqa: BLE001
        print(f"     fact-check skipped ({exc}); number-guard: "
              f"{numbers or 'clean'}. Review before publishing.")

    print(f"saved premium script -> {out}\nRender it: python -m carshorts.produce "
          f"--script-file {out} --spec {spec_path} --stock")
    return str(out)


def main() -> None:
    p = argparse.ArgumentParser(description="Generate a premium, fact-checked script.")
    p.add_argument("--spec", required=True, help="Path to a spec-sheet JSON.")
    p.add_argument("--out", help="Output script JSON (default scripts/<car>_<persona>.script.json).")
    p.add_argument("--persona", default="", choices=["", "bhai", "deadpan", "hype"],
                   help="Channel voice to write in.")
    p.add_argument("--language", default="english", choices=["english", "hinglish", "hindi"])
    p.add_argument("--variants", type=int, default=3, help="How many candidates to generate.")
    p.add_argument("--format", default="spotlight",
                   choices=["spotlight", "vs", "five_things", "mythbust", "base_vs_top"],
                   help="Narrative shell for the video.")
    p.add_argument("--provider", choices=["gemini", "groq", "cerebras", "openrouter", "ollama"],
                   help="LLM backend (or CARSHORTS_LLM). Default gemini.")
    args = p.parse_args()

    sheet = SpecSheet.model_validate_json(Path(args.spec).read_text())
    out = args.out or f"scripts/{_slug(sheet.subject)}_{args.persona or 'default'}.script.json"
    write_premium(args.spec, out, persona=args.persona, language=args.language,
                  variants=args.variants, provider=args.provider, video_format=args.format)


if __name__ == "__main__":
    main()
