"""Renders the Gate 1 review report.

In Milestone 1 the "human gate" is just a readable report, not a web UI (a UI
here would be premature). The report's whole job is to make the human's
verification fast: surface every flagged claim first, show each factual claim
next to the exact source sentence that backs it, and make unsupported claims
impossible to miss.
"""
from __future__ import annotations

from carshorts.core.models import FactCheckReport, Script, SpecSheet, Verdict

_MARK = {
    Verdict.SUPPORTED: "[OK]",
    Verdict.OPINION: "[opinion]",
    Verdict.UNSUPPORTED: ">>> UNSUPPORTED <<<",
    Verdict.CONTRADICTED: ">>> CONTRADICTED <<<",
}


def render_gate1_report(
    script: Script,
    spec_sheet: SpecSheet,
    report: FactCheckReport,
    structural_problems: list[str],
) -> str:
    idx = spec_sheet.fact_index()
    out: list[str] = []
    out.append(f"# Gate 1 review — {script.subject}")
    out.append("")

    # Headline verdict first: a human should know in 2 seconds if this needs work.
    if report.needs_human_attention or structural_problems:
        out.append(f"STATUS: NEEDS ATTENTION — {report.flag_count} flagged claim(s), "
                   f"{len(structural_problems)} structural problem(s).")
    else:
        out.append("STATUS: clean — every factual claim is backed. Skim and approve.")
    out.append("")

    out.append(f"Word count: ~{script.approx_word_count()} "
               f"(target ~150 for 60s).")
    out.append("")

    if structural_problems:
        out.append("## Structural problems (no LLM needed — hard errors)")
        for p in structural_problems:
            out.append(f"- {p}")
        out.append("")

    out.append("## Script")
    for seg in script.segments:
        out.append(f"### {seg.role.upper()}")
        out.append(seg.text)
        out.append("")

    out.append("## Claim-by-claim check")
    # Flagged claims first.
    flagged = [c for c in report.checks
               if c.verdict in (Verdict.UNSUPPORTED, Verdict.CONTRADICTED)]
    clean = [c for c in report.checks if c not in flagged]
    for c in flagged + clean:
        out.append(f"- {_MARK[c.verdict]} {c.claim_text}")
        if c.backing_spec_name and c.backing_spec_name in idx:
            spec = idx[c.backing_spec_name]
            out.append(f"    source: {spec.value} — \"{spec.source_sentence}\"")
            out.append(f"    {spec.source_url}")
        if c.note:
            out.append(f"    note: {c.note}")
    out.append("")
    out.append("Approve? Edit the flagged lines or reject and redraft.")
    return "\n".join(out)
