"""Premium script studio: spec sheet -> best fact-checked script.

  python -m carshorts.writing.writescript --spec specs/tata-nexon.json \
      --persona bhai --language hinglish --variants 3 --provider groq \
      --out data/scripts/nexon_bhai.script.json

Pipeline (script-first — perfect the words before spending render compute):
  1. VARIANTS  — draft N scripts, each from a different opening angle + persona.
  2. JUDGE     — a ruthless editor scores them and picks the best.
  3. EDITOR    — punch up the winner (sharper hook, tighter pacing, better CTA)
                 without adding any unsourced fact.
  4. SAFETY    — structural + number-guard + LLM fact-check; print Gate 1 report.

Output is a .script.json — render it later, free, with:
  python -m carshorts.rendering.produce --script-file <that file> --spec <spec> --stock
"""
from __future__ import annotations

import argparse
from pathlib import Path

from carshorts.adapters.llm import make_llm
from carshorts.core import paths
from carshorts.core.models import SpecSheet
from carshorts.rendering.produce import _apply_extras, _slug
from carshorts.writing import scriptbrain
from carshorts.writing.draft import (
    draft_script,
    enforce_length,
    fact_check,
    judge_scripts,
    structural_citation_check,
    unsourced_features_check,
    unsourced_numbers_check,
)
from carshorts.writing.gate1 import render_gate1_report
from carshorts.writing.prompts import ANGLES, FORMATS


def write_premium(spec_path: str, out_path: str, persona: str = "", language: str = "english",
                  variants: int = 3, provider: str | None = None,
                  video_format: str = "spotlight") -> str:
    sheet = SpecSheet.model_validate_json(Path(spec_path).read_text())
    guidance = _apply_extras(sheet)          # sourced price + value-pick, if any
    from carshorts.core.learnings import load_learnings_guidance
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

    print("3/4  script brain: critique -> revise loop (format-aware)...")
    final = best
    try:
        final, crit = scriptbrain.studio_pass(best, sheet, fmt=video_format, provider=provider)
        print(f"     script brain: {crit.get('verdict')} {crit.get('score')}/10 — "
              f"USP: {crit.get('usp')} | verdict: {crit.get('verdict_line')}")
    except Exception as exc:  # noqa: BLE001 — the brain is best-effort; keep the judged best
        print(f"     script brain pass failed ({exc}); keeping the judged best.")

    # Enforce the Shorts length cap at write-time so a wordy draft can't overshoot
    # 60s and fail the render's length QA (a Punch draft came out ~196 words).
    before_words = final.approx_word_count()
    final = enforce_length(final, sheet, llm)
    if final.approx_word_count() != before_words:
        print(f"     length: trimmed {before_words} -> {final.approx_word_count()} words (Shorts cap)")

    # Save NOW so a later fact-check hiccup can never lose the script.
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(final.model_dump_json(indent=2))

    print("4/4  safety (structural + number-guard + fact-check)...")
    structural = structural_citation_check(final, sheet)
    numbers = unsourced_numbers_check(final, sheet)
    features = unsourced_features_check(final, sheet)
    try:
        report = fact_check(final, sheet, llm)
        print("\n" + render_gate1_report(final, sheet, report,
                                          structural + numbers + features) + "\n")
    except Exception as exc:  # noqa: BLE001 — fact-check is advisory; never blocks the write
        print(f"     fact-check skipped ({exc}); guards: "
              f"{(numbers + features) or 'clean'}. Review before publishing.")

    print(f"saved premium script -> {out}\nRender it: python -m carshorts.rendering.produce "
          f"--script-file {out} --spec {spec_path} --stock")
    return str(out)


def write_options(spec_path: str, n: int = 3, persona: str = "", language: str = "english",
                  provider: str | None = None, video_format: str = "spotlight") -> list[str]:
    """Generate n DISTINCT option scripts (different angles, no judging) for the
    portal's script builder, saved as <slug>_opt{k}.script.json and APPENDED after
    any existing options. Unlike write_premium (which judges + keeps one best),
    this keeps them all so the owner mixes-and-matches beats."""
    import json as _json
    sheet = SpecSheet.model_validate_json(Path(spec_path).read_text())
    base = _apply_extras(sheet)              # sourced price + value-pick (the data context)
    from carshorts.core.learnings import load_learnings_guidance
    craft = load_learnings_guidance()
    if craft:
        base = f"{base}\n\n{craft}" if base else craft
    llm = make_llm(provider)
    slug = _slug(sheet.subject)

    # ANGLE MINER: pick the n strongest DISTINCT angles (format + hook + USP +
    # verdict) from the data; each option is then drafted + auto-revised to ITS
    # format's bar. Falls back to the generic angle rotation if mining is empty.
    mined = scriptbrain.mine_angles(sheet, base, provider=provider, n=n)

    start = 1
    for p in paths.SCRIPTS.glob(f"{slug}_opt*.script.json"):
        try:
            start = max(start, int(p.stem.split("_opt")[-1].split(".")[0]) + 1)
        except ValueError:
            pass
    out_files = []
    for i in range(n):
        k = start + i
        a = mined[i] if i < len(mined) else {}
        fmt_key = a.get("format", video_format)
        ang_lines = [x for x in (
            (f"HOOK ANGLE: {a['hook']}" if a.get("hook") else ""),
            (f"THE ONE USP: {a['usp']}" if a.get("usp") else ""),
            (f"LAND THIS VERDICT: {a['verdict']}" if a.get("verdict") else ""),
        ) if x]
        angle = "\n".join(ang_lines) if ang_lines else ANGLES[(k - 1) % len(ANGLES)]
        fmt_shell = FORMATS.get(fmt_key, "")
        guidance = f"{base}\n\n{fmt_shell}" if fmt_shell else base
        s = draft_script(sheet, llm, language=language, guidance=guidance,
                         persona=persona, angle=angle)
        # Script Brain: auto-revise this option to its format bar (clear USP +
        # decisive verdict), then keep its critique for the owner's Gate-1 pick.
        s, crit = scriptbrain.studio_pass(s, sheet, fmt=fmt_key, provider=provider)
        s = enforce_length(s, sheet, llm)
        d = _json.loads(s.model_dump_json())
        usp = (crit.get("usp") or "").strip()
        score = crit.get("score")
        label = usp if usp and usp.upper() != "NONE" else "fresh take"
        d["_angle"] = f"Opt {k} · {label}" + (f" · {score}/10" if score else "")
        d["_critique"] = crit          # surfaced per-option in the portal (Gate 1)
        d["_format"] = fmt_key         # tag for the learning loop (angle/format perf)
        out = paths.SCRIPTS / f"{slug}_opt{k}.script.json"
        out.write_text(_json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
        out_files.append(str(out))
        print(f"  wrote {out.name}  score={score} usp={usp[:40]}")
    return out_files


def main() -> None:
    p = argparse.ArgumentParser(description="Generate a premium, fact-checked script.")
    p.add_argument("--spec", required=True, help="Path to a spec-sheet JSON.")
    p.add_argument("--out", help="Output script JSON (default data/scripts/<car>_<persona>.script.json).")
    p.add_argument("--persona", default="", choices=["", "bhai", "deadpan", "hype"],
                   help="Channel voice to write in.")
    p.add_argument("--language", default="english", choices=["english", "hinglish", "hindi"])
    p.add_argument("--variants", type=int, default=3, help="How many candidates to generate.")
    p.add_argument("--format", default="spotlight",
                   choices=["spotlight", "vs", "five_things", "mythbust", "base_vs_top"],
                   help="Narrative shell for the video.")
    p.add_argument("--provider", choices=["gemini", "groq", "cerebras", "openrouter", "ollama"],
                   help="LLM backend (or CARSHORTS_LLM). Default gemini.")
    p.add_argument("--options", type=int, default=0,
                   help="Generate N option scripts (opt files) for the portal builder, not one best.")
    args = p.parse_args()

    if args.options:
        write_options(args.spec, n=args.options, persona=args.persona, language=args.language,
                      provider=args.provider, video_format=args.format)
        return
    sheet = SpecSheet.model_validate_json(Path(args.spec).read_text())
    out = args.out or str(paths.SCRIPTS / f"{_slug(sheet.subject)}_{args.persona or 'default'}.script.json")
    write_premium(args.spec, out, persona=args.persona, language=args.language,
                  variants=args.variants, provider=args.provider, video_format=args.format)


if __name__ == "__main__":
    main()
