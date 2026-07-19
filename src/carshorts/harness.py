"""Milestone 1's exit criterion: measure how often a real model hallucinates.

The demo proves the *mechanism* (writer + separate skeptic + structural check).
It does NOT prove the *number* the whole "95% automated" ambition rests on:
across many real cars, how often does the writer assert a fact the spec sheet
does not support?

This harness replays every saved spec sheet (specs/*.json, produced by
`python -m carshorts.crawl`) through the real pipeline and tallies:

  - flag rate     : share of sheets with >=1 UNSUPPORTED or CONTRADICTED claim
  - contradictions: the serious ones (claim disagrees with a real spec)
  - structural    : cited_spec_names pointing at specs that don't exist

  python -m carshorts.harness                 # real Gemini, specs/ dir
  python -m carshorts.harness --dir specs --throttle 30

The result is a GO / NO-GO signal, not a decision: a human reads it. Low flag
rate -> Gate 1 can stay light, automation is viable. High rate -> the human
stays the quality firewall and "automatic daily" is off the table until the
writer or the spec sheets improve.

Free-tier reality: Gemini free tier allows ~5 requests/min and each sheet costs
2 calls (draft + fact-check). --throttle sleeps between sheets to stay under
that, and 429s are retried with backoff rather than crashing the run.
"""
from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .adapters.llm import LLMClient, make_llm
from .models import FactCheckReport, SpecSheet, Verdict
from .stages.pipeline import draft_script, fact_check, structural_citation_check


@dataclass
class SheetResult:
    subject: str
    spec_count: int
    word_count: int = 0
    unsupported: int = 0
    contradicted: int = 0
    structural_problems: int = 0
    error: str = ""
    # The actual flagged claim texts — the real signal. Counts tell us HOW MANY;
    # these tell us WHAT KIND (a fabricated number vs harmless framing).
    flagged_claims: list[str] = field(default_factory=list)
    script_text: str = ""

    @property
    def flagged(self) -> bool:
        return self.unsupported > 0 or self.contradicted > 0


def load_sheets(dir_path: str) -> list[SpecSheet]:
    paths = sorted(Path(dir_path).glob("*.json"))
    sheets = []
    for p in paths:
        sheets.append(SpecSheet.model_validate_json(p.read_text()))
    return sheets


def _is_rate_limit(exc: Exception) -> bool:
    text = str(exc).lower()
    return "429" in text or "resourceexhausted" in text or "quota" in text


def evaluate(sheet: SpecSheet, llm: LLMClient, throttle: float, backoff: float,
             retries: int = 2) -> SheetResult:
    """Run one sheet through draft -> structural check -> fact-check.

    Retries the sheet on rate-limit (429) with backoff instead of crashing.
    """
    attempt = 0
    while True:
        try:
            script = draft_script(sheet, llm)
            structural = structural_citation_check(script, sheet)
            report: FactCheckReport = fact_check(script, sheet, llm)
            flagged_claims = [
                f"[{c.verdict.value}] {c.claim_text}"
                + (f"  — {c.note}" if c.note else "")
                for c in report.checks
                if c.verdict in (Verdict.UNSUPPORTED, Verdict.CONTRADICTED)
            ]
            return SheetResult(
                subject=sheet.subject,
                spec_count=len(sheet.specs),
                word_count=script.approx_word_count(),
                unsupported=sum(1 for c in report.checks if c.verdict == Verdict.UNSUPPORTED),
                contradicted=sum(1 for c in report.checks if c.verdict == Verdict.CONTRADICTED),
                structural_problems=len(structural),
                flagged_claims=flagged_claims,
                script_text=script.full_text,
            )
        except Exception as exc:  # noqa: BLE001 — harness must survive one bad sheet
            if _is_rate_limit(exc) and attempt < retries:
                attempt += 1
                print(f"    rate-limited, backing off {backoff:.0f}s "
                      f"(attempt {attempt}/{retries})...")
                time.sleep(backoff)
                continue
            return SheetResult(
                subject=sheet.subject,
                spec_count=len(sheet.specs),
                error=str(exc)[:200],
            )


def summarize(results: list[SheetResult]) -> str:
    ok = [r for r in results if not r.error]
    errored = [r for r in results if r.error]
    evaluated = len(ok)
    flagged = [r for r in ok if r.flagged]
    total_unsupported = sum(r.unsupported for r in ok)
    total_contradicted = sum(r.contradicted for r in ok)
    structural = [r for r in ok if r.structural_problems]

    lines = ["", "=" * 60, "HALLUCINATION HARNESS — RESULT", "=" * 60, ""]
    lines.append(f"Sheets evaluated : {evaluated}"
                 + (f"  ({len(errored)} errored)" if errored else ""))
    if evaluated:
        rate = 100 * len(flagged) / evaluated
        lines.append(f"Sheets flagged   : {len(flagged)}/{evaluated}  ({rate:.0f}%)")
    lines.append(f"Unsupported clms : {total_unsupported}")
    lines.append(f"Contradictions   : {total_contradicted}   <-- serious")
    lines.append(f"Structural probs : {len(structural)} sheet(s)")
    lines.append("")
    lines.append("Per sheet:")
    for r in results:
        if r.error:
            lines.append(f"  [ERR ] {r.subject}: {r.error}")
        else:
            tag = "FLAG" if r.flagged else " ok "
            lines.append(
                f"  [{tag}] {r.subject}: {r.spec_count} specs, ~{r.word_count} words, "
                f"{r.unsupported} unsupported, {r.contradicted} contradicted, "
                f"{r.structural_problems} structural"
            )
    lines.append("")

    # The actual flagged claims — the real signal for the go/no-go call.
    flagged_with_claims = [r for r in ok if r.flagged_claims]
    if flagged_with_claims:
        lines.append("What the model actually got flagged for:")
        for r in flagged_with_claims:
            lines.append(f"  {r.subject}:")
            for claim in r.flagged_claims:
                lines.append(f"    - {claim}")
        lines.append("")

    # Soft signal — the human makes the call. The KIND of flag matters more than
    # the rate: a contradicted number is dangerous; an unsupported bit of framing
    # ("it's an SUV") is harmless and prompt-fixable.
    if evaluated:
        rate = len(flagged) / evaluated
        if total_contradicted > 0:
            verdict = ("NO-GO (for now): contradictions mean the writer stated something "
                       "that DISAGREES with a real spec. That is the dangerous kind. "
                       "Fix before trusting automation.")
        elif total_unsupported == 0:
            verdict = ("Strong GO signal: nothing flagged. Gate 1 can stay light.")
        else:
            verdict = (
                f"MIXED — but no fabricated numbers (0 contradictions). The writer adds "
                f"UNSUPPORTED claims ({total_unsupported} across {len(flagged)}/{evaluated} "
                f"sheets) — read them above: if they are framing/opinion ('it's an SUV'), "
                f"tighten the writer prompt and automation stays viable; if they are invented "
                f"facts, Gate 1 must stay heavy.")
        lines.append("VERDICT: " + verdict)
    else:
        lines.append("VERDICT: no sheets evaluated — crawl some specs first "
                     "(python -m carshorts.crawl \"Car Name\").")
    lines.append("=" * 60)
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure model hallucination rate.")
    parser.add_argument("--dir", default="specs", help="Dir of spec-sheet JSON (default: specs).")
    parser.add_argument("--throttle", type=float, default=30.0,
                        help="Seconds to sleep between sheets (free tier ~5 req/min, 2 calls/sheet).")
    parser.add_argument("--backoff", type=float, default=65.0,
                        help="Seconds to wait after a 429 before retrying a sheet.")
    parser.add_argument("--report", default="harness_report.json",
                        help="Where to write the full per-sheet report (default: harness_report.json).")
    parser.add_argument("--provider", choices=["gemini", "groq", "cerebras", "openrouter", "ollama"],
                        help="LLM backend (or set CARSHORTS_LLM). Default gemini.")
    args = parser.parse_args()

    sheets = load_sheets(args.dir)
    if not sheets:
        print(f"No spec sheets in {args.dir}/. Run: python -m carshorts.crawl \"Tata Nexon\"")
        return

    llm = make_llm(args.provider)
    results: list[SheetResult] = []
    for i, sheet in enumerate(sheets):
        print(f"[{i + 1}/{len(sheets)}] {sheet.subject} ({len(sheet.specs)} specs)...")
        results.append(evaluate(sheet, llm, args.throttle, args.backoff))
        if i < len(sheets) - 1 and args.throttle > 0:
            time.sleep(args.throttle)

    Path(args.report).write_text(json.dumps([asdict(r) for r in results], indent=2))
    print(summarize(results))
    print(f"\nFull report written to {args.report}")


if __name__ == "__main__":
    main()
