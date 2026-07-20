"""The four stages of the Milestone 1 slice.

Each stage is a function: typed input -> typed output. No stage knows which
LLM provider it's using (it gets an LLMClient). No stage mutates global state.
This keeps every stage independently testable with a MockLLMClient.

Spec collection in this slice uses a provided-text extractor rather than live
crawling, so the slice is runnable offline and deterministic. Swapping in a
real fetcher later is a change behind the same function signature.
"""
from __future__ import annotations

import re

from ..adapters.llm import LLMClient
from ..models import (
    ClaimCheck,
    FactCheckReport,
    NewsItem,
    Script,
    ScriptSegment,
    SpecSheet,
)
from ..prompts.templates import (
    DRAFT_SYSTEM,
    EDITOR_SYSTEM,
    FACTCHECK_SYSTEM,
    JUDGE_SYSTEM,
    LANGUAGE_INSTRUCTIONS,
    PERSONAS,
    RANK_SYSTEM,
    render_spec_sheet,
)


# ---------------------------------------------------------------------------
# Stage 1b: rank (discovery itself is a feed pull; ranking is the LLM judgment)
# ---------------------------------------------------------------------------
def _rows(data) -> list:
    """Coerce an LLM JSON response into a list of row dicts.

    Providers disagree on shape: Gemini returns a bare array, but OpenAI-style
    JSON mode (Groq, Ollama, ...) forces a top-level OBJECT, so the array comes
    back wrapped like {"claims": [...]} or {"results": [...]}. Accept both, and
    keep only dict rows so a stray string can't crash the caller.
    """
    if isinstance(data, dict):
        for value in data.values():
            if isinstance(value, list):
                data = value
                break
        else:
            data = [data]
    if not isinstance(data, list):
        return []
    return [row for row in data if isinstance(row, dict)]


def rank_stories(items: list[NewsItem], llm: LLMClient) -> list[NewsItem]:
    """Score each story for viral potential and return them sorted, high first."""
    if not items:
        return []
    payload = "\n".join(
        f'- url={i.url} title="{i.title}" summary="{i.summary}"' for i in items
    )
    scored = _rows(llm.complete_json(RANK_SYSTEM, f"STORIES:\n{payload}"))
    by_url = {str(i.url): i for i in items}
    for row in scored:
        item = by_url.get(row["url"])
        if item:
            item.virality_score = float(row["score"])
            item.virality_reasons = list(row.get("reasons", []))
    return sorted(items, key=lambda i: i.virality_score, reverse=True)


# ---------------------------------------------------------------------------
# Stage 3: draft script (constrained to the spec sheet)
# ---------------------------------------------------------------------------
def _script_from_data(data: dict, default_subject: str) -> Script:
    segments = [
        ScriptSegment(
            role=seg["role"],
            text=seg["text"],
            cited_spec_names=seg.get("cited_spec_names", []),
        )
        for seg in data.get("segments", [])
    ]
    return Script(subject=data.get("subject", default_subject), segments=segments)


def draft_script(spec_sheet: SpecSheet, llm: LLMClient, language: str = "english",
                 guidance: str = "", persona: str = "", angle: str = "") -> Script:
    language_line = LANGUAGE_INSTRUCTIONS.get(language.lower(), LANGUAGE_INSTRUCTIONS["english"])
    persona_line = PERSONAS.get(persona.lower(), "") if persona else ""
    blocks = [b for b in (guidance, persona_line, angle) if b]
    extra = ("\n\n" + "\n".join(blocks)) if blocks else ""
    user = (
        f"{render_spec_sheet(spec_sheet)}"
        f"{extra}\n\n"
        f"{language_line}\n\n"
        "Write the Short script now, using ONLY the specs above."
    )
    data = llm.complete_json(DRAFT_SYSTEM, user)
    return _script_from_data(data, spec_sheet.subject)


def judge_scripts(scripts: list[Script], llm: LLMClient) -> tuple[int, str]:
    """Score candidate scripts and return (best_index, why). Falls back to 0."""
    if len(scripts) == 1:
        return 0, "only candidate"
    numbered = "\n\n".join(f"### SCRIPT {i}\n{s.full_text}" for i, s in enumerate(scripts))
    result = llm.complete_json(JUDGE_SYSTEM, numbered)
    if isinstance(result, dict):
        idx = int(result.get("best_index", 0))
        if 0 <= idx < len(scripts):
            return idx, str(result.get("why", ""))
    return 0, "judge fallback"


def punch_up_script(script: Script, spec_sheet: SpecSheet, llm: LLMClient) -> Script:
    """Editor pass: sharpen the winning script without adding unsourced facts."""
    user = (
        f"{render_spec_sheet(spec_sheet)}\n\n"
        f"SCRIPT:\n{script.model_dump_json()}\n\n"
        "Punch up this script now."
    )
    data = llm.complete_json(EDITOR_SYSTEM, user)
    return _script_from_data(data, script.subject)


# ---------------------------------------------------------------------------
# Stage 4: fact-check (separate skeptic pass)
# ---------------------------------------------------------------------------
def fact_check(script: Script, spec_sheet: SpecSheet, llm: LLMClient) -> FactCheckReport:
    user = (
        f"{render_spec_sheet(spec_sheet)}\n\n"
        f"SCRIPT:\n{script.full_text}\n\n"
        "Check the script against the spec sheet now."
    )
    rows = _rows(llm.complete_json(FACTCHECK_SYSTEM, user))
    checks = [
        ClaimCheck(
            claim_text=r["claim_text"],
            verdict=r["verdict"],
            backing_spec_name=r.get("backing_spec_name"),
            note=r.get("note", ""),
        )
        for r in rows
        if "claim_text" in r and "verdict" in r
    ]
    return FactCheckReport(subject=script.subject, checks=checks)


# ---------------------------------------------------------------------------
# A cheap deterministic cross-check that does NOT need an LLM, run alongside the
# LLM fact-checker as a second opinion. If the script's cited_spec_names point
# at specs that don't exist in the sheet, that's a hard error no model needed.
# ---------------------------------------------------------------------------
def structural_citation_check(script: Script, spec_sheet: SpecSheet) -> list[str]:
    """Return a list of structural problems found without any LLM call."""
    known = set(spec_sheet.fact_index().keys())
    problems: list[str] = []
    for seg in script.segments:
        for name in seg.cited_spec_names:
            if name not in known:
                problems.append(
                    f'Segment "{seg.role}" cites unknown spec "{name}" '
                    f"(not in spec sheet)."
                )
    return problems


# A number attached to a unit, or preceded by a currency symbol — i.e. the shape
# of a spec claim, not an incidental integer like a model year or a count.
_UNIT = (r"bhp|hp|kw|ps|n⋅m|n·m|n-m|nm|cc|litres?|liters?|kmpl|mpg|km/?h|kmph|"
         r"mph|seconds?|secs?|lakh|crore")
_NUM_UNIT = re.compile(rf"(?P<num>\d[\d,]*\.?\d*)\s*(?:{_UNIT})\b", re.I)
_CURRENCY_NUM = re.compile(r"(?:₹|rs\.?|\$|€|£)\s?(?P<num>\d[\d,]*\.?\d*)", re.I)


def _digits(text: str) -> str:
    return re.sub(r"[^0-9.]", "", text.lower())


def unsourced_numbers_check(script: Script, spec_sheet: SpecSheet) -> list[str]:
    """Deterministic (no-LLM) guard against fabricated figures.

    Every number-with-a-unit (or a price) in the script must trace to a spec
    value or its source sentence. Anything that doesn't is a likely
    hallucination — flagged regardless of which model wrote or fact-checked the
    script. This is the model-independent backstop for the accuracy guarantee:
    an LLM skeptic can be fooled or too weak; digit arithmetic cannot.
    """
    allowed = _digits(" ".join(
        f"{s.value} {s.source_sentence}" for s in spec_sheet.specs
    ))
    problems: list[str] = []
    seen: set[str] = set()
    for seg in script.segments:
        for match in list(_NUM_UNIT.finditer(seg.text)) + list(_CURRENCY_NUM.finditer(seg.text)):
            token = match.group(0).strip()
            number = _digits(match.group("num"))
            if not number or number in seen:
                continue
            if number not in allowed:
                seen.add(number)
                problems.append(
                    f'Number "{token}" (in {seg.role}) is NOT in any spec — '
                    f"possible fabrication."
                )
    return problems
