"""Tests for the Milestone 1 slice.

The point of these tests is not coverage theatre. They lock in the two
behaviours the whole product depends on:
  1. The fact-checker flags a claim the spec sheet does not support.
  2. The structural check catches a citation pointing at a nonexistent spec
     with no LLM involved at all.
All LLM calls are mocked, so the suite is fast, free, and deterministic.
"""
from __future__ import annotations

import pytest

from carshorts.adapters.llm import MockLLMClient
from carshorts.models import Script, ScriptSegment, Spec, SpecSheet, Verdict
from carshorts.stages.pipeline import (
    draft_script,
    fact_check,
    rank_stories,
    structural_citation_check,
)


@pytest.fixture
def sheet() -> SpecSheet:
    return SpecSheet(
        subject="Test Car",
        specs=[
            Spec(name="power", value="150 bhp",
                 source_url="https://example.com/a",
                 source_sentence="It makes 150 bhp."),
        ],
    )


def test_draft_uses_only_provided_specs(sheet):
    draft = (
        '{"subject":"Test Car","segments":['
        '{"role":"hook","text":"150 bhp of fun.","cited_spec_names":["power"]},'
        '{"role":"cta","text":"Subscribe.","cited_spec_names":[]}]}'
    )
    llm = MockLLMClient({"Write the Short script": draft})
    script = draft_script(sheet, llm)
    assert script.subject == "Test Car"
    assert script.segments[0].cited_spec_names == ["power"]


def test_factcheck_flags_unsupported_claim(sheet):
    script = Script(subject="Test Car", segments=[
        ScriptSegment(role="body", text="It does 0-100 in 7s.", cited_spec_names=[]),
    ])
    check = (
        '[{"claim_text":"0-100 in 7s","verdict":"unsupported",'
        '"backing_spec_name":null,"note":"no acceleration spec"}]'
    )
    llm = MockLLMClient({"Check the script": check})
    report = fact_check(script, sheet, llm)
    assert report.needs_human_attention
    assert report.flag_count == 1
    assert report.checks[0].verdict == Verdict.UNSUPPORTED


def test_structural_check_catches_phantom_citation(sheet):
    # Script cites a spec that does not exist in the sheet — caught with no LLM.
    script = Script(subject="Test Car", segments=[
        ScriptSegment(role="hook", text="Blazing fast!",
                      cited_spec_names=["top_speed"]),
    ])
    problems = structural_citation_check(script, sheet)
    assert len(problems) == 1
    assert "top_speed" in problems[0]


def test_structural_check_passes_valid_citation(sheet):
    script = Script(subject="Test Car", segments=[
        ScriptSegment(role="hook", text="150 bhp!", cited_spec_names=["power"]),
    ])
    assert structural_citation_check(script, sheet) == []


def test_ranking_sorts_by_virality(sheet):
    from carshorts.models import NewsItem
    items = [
        NewsItem(title="Boring recall notice", url="https://example.com/1",
                 source_name="X", summary="minor recall"),
        NewsItem(title="All-new flagship launch", url="https://example.com/2",
                 source_name="Y", summary="big launch"),
    ]
    ranked_json = (
        '[{"url":"https://example.com/1","score":0.1,"reasons":["recall"]},'
        '{"url":"https://example.com/2","score":0.9,"reasons":["launch"]}]'
    )
    llm = MockLLMClient({"STORIES:": ranked_json})
    ranked = rank_stories(items, llm)
    assert str(ranked[0].url) == "https://example.com/2"
    assert ranked[0].virality_score == 0.9
