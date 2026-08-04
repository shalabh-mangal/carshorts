"""Script Brain — format-aware critique + revise of a SCRIPT, upstream of render.

The render critic (agents/critic.py) judges a finished video; by then a weak USP
or a missing verdict is already baked in. This judges the SCRIPT TEXT so it's
caught and fixed BEFORE we spend a render — and it grades against the chosen
FORMAT's bar (owner: the "engaging" bar depends on the video type), plus TASTE.md
and the proven learnings. `studio_pass` runs the draft -> critique -> revise loop
until the script clears its format bar, never keeping a revision that introduces
an unsourced fact. Free (groq/gemini).
"""
from __future__ import annotations

import json

from carshorts.adapters.llm import make_llm
from carshorts.core import paths
from carshorts.core.learnings import load_learnings_guidance
from carshorts.core.models import Script, SpecSheet
from carshorts.writing.draft import (
    _script_from_data,
    structural_citation_check,
    unsourced_features_check,
    unsourced_numbers_check,
)
from carshorts.writing.prompts import render_spec_sheet

BAR = 8          # score (1-10) a script must clear to stop revising
MAX_ITER = 3     # revise attempts before we ship the best we have

# What makes THIS format engaging — the adaptive bar the critique grades on.
FORMAT_RUBRICS = {
    "spotlight": "SPOTLIGHT: a hero NUMBER lands in the first 2s; exactly ONE clear "
                 "USP (never a feature dump); a hot-take VERDICT that takes a side.",
    "vs": "VS BATTLE: a bold contrast hook; a fair head-to-head on 2-3 sourced "
          "dimensions; a DECISIVE winner (never a fence-sit); a rivalry poll CTA.",
    "five_things": "FIVE THINGS: tease #5 in the hook ('number 5 changes the math'); "
                   "escalating items; #5 must be the strongest payoff.",
    "mythbust": "MYTH-BUST: open on a belief people hold; bust or confirm it with a "
                "SURPRISING sourced fact; end with what to do instead.",
    "base_vs_top": "BASE vs TOP: what the extra money actually buys, feature by "
                   "feature; a verdict on who should genuinely pay the difference.",
    "facelift": "FACELIFT vs OLD: what actually changed; a verdict on whether the "
                "update is worth it over the predecessor.",
    "upcoming": "UPCOMING: the ONE reason it's worth the wait; a clear 'wait or buy "
                "now' verdict.",
}
_DEFAULT_RUBRIC = FORMAT_RUBRICS["spotlight"]


def rubric_for(fmt: str) -> str:
    return FORMAT_RUBRICS.get((fmt or "spotlight").lower(), _DEFAULT_RUBRIC)


def _taste() -> str:
    for p in (paths.ROOT / "charters" / "TASTE.md", paths.ROOT / "TASTE.md"):
        if p.exists():
            return p.read_text(encoding="utf-8")[:3500]
    return ""


def _summary(script: Script) -> str:
    return json.dumps({
        "subject": script.subject,
        "word_count": script.approx_word_count(),
        "beats": [{"role": s.role, "text": s.text, "cited": s.cited_spec_names}
                  for s in script.segments],
    }, ensure_ascii=False, indent=1)


def critique(script: Script, sheet: SpecSheet | None = None,
             fmt: str = "spotlight", provider: str | None = None) -> dict:
    """Grade a SCRIPT against its format bar + TASTE + learnings. Returns
    {verdict, score, usp, verdict_line, summary, strengths, issues:[{beat,problem,fix}]}."""
    system = (
        _taste() + "\n\n"
        "You are the SCRIPT BRAIN — a demanding short-form creative director judging a "
        "car-Shorts SCRIPT BEFORE it becomes a video. The single most important test: does "
        "it land ONE clear USP and a DECISIVE verdict that makes a viewer stop, care, and "
        "comment? A script that hedges or feature-dumps fails. Grade against THIS video's "
        "format bar:\n" + rubric_for(fmt) + "\n\n"
        "Also weigh: hook stopping-power in the first 2s, tightness (~90 words / ~30s), FRESH "
        "non-recycled humor, and a comment-bait rivalry CTA. Be specific and honest, and name "
        "what genuinely works.\n\nPROVEN LEARNINGS:\n" + load_learnings_guidance(16)
    )
    user = (
        "SCRIPT:\n" + _summary(script) + "\n\nReturn ONLY JSON:\n"
        '{"verdict":"ship|revise|block","score":<1-10>,'
        '"usp":"the ONE USP in <=8 words, or NONE","verdict_line":"the decisive take in '
        '<=10 words, or NONE","summary":"one honest sentence","strengths":["..."],'
        '"issues":[{"beat":"<role>","problem":"...","fix":"..."}]}'
    )
    try:
        c = make_llm(provider).complete_json(system, user)
        if isinstance(c, list):
            c = c[0] if c else {}
    except Exception as exc:  # noqa: BLE001 — the brain is advisory, never blocks a write
        c = {"verdict": "revise", "score": None,
             "summary": f"script brain unavailable ({str(exc)[:80]})",
             "strengths": [], "issues": []}
    return c if isinstance(c, dict) else {}


def revise(script: Script, sheet: SpecSheet, crit: dict,
           fmt: str = "spotlight", provider: str | None = None) -> Script:
    """Rewrite the script to fix the critique's issues and nail the format bar,
    adding NO fact not already in the spec sheet. Returns the revised Script (or
    the original on error)."""
    fixes = "; ".join(f"[{i.get('beat', '')}] {i.get('fix', '')}"
                      for i in (crit.get("issues") or []) if i.get("fix"))
    system = (
        "You are a script doctor for car YouTube Shorts. Rewrite the SCRIPT to fix the "
        "listed ISSUES and hit this format's bar:\n" + rubric_for(fmt) + "\n"
        "Sharpen to ONE clear USP and a DECISIVE verdict; keep the same section roles and "
        "language; keep it tight (~90 words). CRITICAL: introduce NO number, price, spec, or "
        "named feature/equipment that is not in the SPEC SHEET, and keep each beat's "
        "cited_spec_names. Opinions and verdicts are encouraged but must read as clearly "
        "subjective. Return ONLY JSON:\n"
        '{"subject":"...","segments":[{"role":"...","text":"...","cited_spec_names":["..."]}]}'
    )
    user = (
        render_spec_sheet(sheet) + "\n\nISSUES TO FIX:\n" + (fixes or "sharpen the USP and the verdict")
        + "\n\nCURRENT SCRIPT:\n" + script.model_dump_json()
    )
    try:
        data = make_llm(provider).complete_json(system, user)
        revised = _script_from_data(data, script.subject)
        return revised if revised.segments else script
    except Exception:  # noqa: BLE001 — a failed revise just keeps the current script
        return script


def _guards_clean(script: Script, sheet: SpecSheet | None) -> bool:
    if sheet is None:
        return True
    return not (structural_citation_check(script, sheet)
                + unsourced_numbers_check(script, sheet)
                + unsourced_features_check(script, sheet))


def studio_pass(script: Script, sheet: SpecSheet | None = None, fmt: str = "spotlight",
                provider: str | None = None, max_iter: int = MAX_ITER,
                bar: int = BAR) -> tuple[Script, dict]:
    """draft -> critique -> revise loop until the script clears its format bar.
    Never keeps a revision that breaks sourcing (unsourced number/feature) or comes
    back empty. Returns (best_script, its_critique)."""
    crit = critique(script, sheet, fmt, provider)
    for _ in range(max_iter):
        if crit.get("verdict") == "ship" or (crit.get("score") or 0) >= bar:
            break
        cand = revise(script, sheet, crit, fmt, provider)
        if not cand.segments or not _guards_clean(cand, sheet):
            break                       # bad revision — keep the last clean script
        script = cand
        crit = critique(script, sheet, fmt, provider)
    return script, crit
