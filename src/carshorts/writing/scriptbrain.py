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

BAR = 8            # score (1-10) a script must clear to stop revising
MAX_ITER = 3       # revise attempts before we ship the best we have
REQUIRED_ROLES = ["hook", "spec", "value", "peak", "cta"]
MIN_WORDS = 55     # a real ~30s narration; thinner reads as captions, not a script


def _structural_issues(script: Script) -> list[dict]:
    """Deterministic completeness checks the LLM critique can miss — a script MUST
    be a full 5-beat, ~30s narration with the like/share/subscribe CTA. Returns
    issue dicts (empty = structurally sound)."""
    issues: list[dict] = []
    roles = [s.role for s in script.segments]
    missing = [r for r in REQUIRED_ROLES if r not in roles]
    if missing:
        issues.append({"beat": "structure",
                       "problem": f"missing beats: {', '.join(missing)}",
                       "fix": "write ALL five beats — hook, spec, value, peak, cta"})
    wc = script.approx_word_count()
    if wc < MIN_WORDS:
        issues.append({"beat": "length",
                       "problem": f"only {wc} words — too thin for ~30s (reads as captions)",
                       "fix": "expand to ~70-90 words with vivid, specific spoken lines"})
    cta = next((s.text.lower() for s in script.segments if s.role == "cta"), "")
    if "subscribe" not in cta:
        issues.append({"beat": "cta",
                       "problem": "CTA is missing the like/share/subscribe ask",
                       "fix": "end the CTA with 'like, share, subscribe' plus a rivalry poll"})
    return issues

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


def mine_angles(sheet: SpecSheet, context: str = "", provider: str | None = None,
                n: int = 3) -> list[dict]:
    """ANGLE MINER — dig into the sourced data + news + learnings and surface the n
    STRONGEST, DISTINCT angles for a Short. Each = {format, hook, usp, verdict, why}.
    This is where creativity starts: it reasons about what's genuinely surprising or
    argument-worthy in THIS car's data (a price that undercuts a rival, a spec gap,
    a reborn-icon story, a facelift-worth-it question) and picks the best FORMAT per
    angle. Returns [] on failure (caller falls back to generic angles)."""
    system = (
        "You are the ANGLE MINER — a viral short-form strategist for an Indian car "
        "channel. From the car's SOURCED data + news below, find the "
        f"{n} STRONGEST, DISTINCT angles for a YouTube Short. For each, choose the best "
        "FORMAT from [" + ", ".join(FORMAT_RUBRICS) + "], a scroll-stopping HOOK, the ONE "
        "USP, the DECISIVE verdict it lands, and WHY it can go viral. Reason about what's "
        "genuinely surprising or argument-worthy — never a generic template. Prefer DISTINCT "
        "formats across the angles. Ground every choice in the proven learnings.\n\n"
        "PROVEN LEARNINGS:\n" + load_learnings_guidance(14)
    )
    user = (
        render_spec_sheet(sheet) + (("\n\n" + context) if context else "")
        + f"\n\nReturn ONLY JSON with up to {n} angles:\n"
        '{"angles":[{"format":"...","hook":"...","usp":"...","verdict":"...","why":"..."}]}'
    )
    try:
        data = make_llm(provider).complete_json(system, user)
        angles = data.get("angles", []) if isinstance(data, dict) else data
        out: list[dict] = []
        for a in (angles or [])[:n]:
            if not isinstance(a, dict):
                continue
            a["format"] = a["format"] if a.get("format") in FORMAT_RUBRICS else "spotlight"
            out.append(a)
        return out
    except Exception:  # noqa: BLE001 — mining is best-effort; caller uses generic angles
        return []


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
        "non-recycled humor, and a comment-bait rivalry CTA. CRITICAL RETENTION TEST — the SPEC "
        "beat is the channel's #1 drop-off (55-81% of viewers leave there): the spec must BRIDGE "
        "and ESCALATE the hook's tension and land as a PAYOFF ('here's the crazy part…'), in ONE "
        "tight line — not a flat number recital or fact-dump. Flag a spec beat that deflates the "
        "hook. Be specific and honest, and name what genuinely works.\n\nPROVEN LEARNINGS:\n"
        + load_learnings_guidance(16)
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
    if not isinstance(c, dict):
        c = {}
    # deterministic completeness overrides: a thin/incomplete script can never
    # "ship", no matter what the LLM said — fold the structural fixes in and cap
    # the score so the studio loop keeps revising until it's whole.
    struct = _structural_issues(script)
    if struct:
        c["issues"] = struct + (c.get("issues") or [])
        c["verdict"] = "revise"
        c["score"] = min(c.get("score") or 0, 4)
    return c


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
        "Sharpen to ONE clear USP and a DECISIVE verdict. REQUIRED structure: write ALL FIVE "
        "beats — hook, spec, value, peak, cta — as full spoken lines totalling ~70-90 words "
        "(never terse captions), and the CTA MUST include the exact words 'like, share, "
        "subscribe' plus a rivalry poll ('X or Y? comment 1 or 2'). RETENTION-CRITICAL: the "
        "SPEC beat is where most viewers leave — it MUST bridge and ESCALATE the hook's tension "
        "and read as the payoff (open with the surprise, e.g. 'here's the crazy part…', then the "
        "number), ONE tight line, never a flat fact-dump. Keep the language. "
        "CRITICAL: introduce NO number, price, spec, or named feature/equipment that is not in "
        "the SPEC SHEET, and keep each beat's cited_spec_names. Verdicts/opinions are encouraged "
        "but must read as clearly subjective. Return ONLY JSON:\n"
        '{"subject":"...","segments":[{"role":"hook|spec|value|peak|cta","text":"...","cited_spec_names":["..."]}]}'
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
