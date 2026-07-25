"""Runnable entry point for the Milestone 1 slice.

  python -m carshorts.run                 # runs the built-in demo spec sheet
  python -m carshorts.run --real          # uses GeminiLLMClient (needs GEMINI_API_KEY)

The default uses a MockLLMClient with a deliberately FLAWED demo script — one
that sneaks in an unsupported figure — so you can see Gate 1 actually catch a
hallucination on the very first run. Run with --real to point at a live model.
"""
from __future__ import annotations

import argparse

from carshorts.adapters.llm import GeminiLLMClient, LLMClient, MockLLMClient
from carshorts.core.models import Spec, SpecSheet
from carshorts.writing.draft import draft_script, fact_check, structural_citation_check
from carshorts.writing.gate1 import render_gate1_report


def demo_spec_sheet() -> SpecSheet:
    return SpecSheet(
        subject="Mahindra Thar Roxx 2024",
        specs=[
            Spec(name="power", value="172 bhp",
                 source_url="https://example.com/thar-roxx",
                 source_sentence="The 2.0L turbo-petrol Thar Roxx makes 172 bhp."),
            Spec(name="price_ex_showroom", value="Rs 12.99 lakh",
                 source_url="https://example.com/thar-roxx-price",
                 source_sentence="Prices start at Rs 12.99 lakh ex-showroom."),
        ],
    )


def _mock_with_planted_hallucination() -> MockLLMClient:
    # The drafted script asserts a 0-100 time that is NOT in the spec sheet.
    draft = (
        '{"subject":"Mahindra Thar Roxx 2024","segments":['
        '{"role":"hook","text":"The Thar Roxx just changed the game with 172 bhp.",'
        '"cited_spec_names":["power"]},'
        '{"role":"body","text":"Starting at Rs 12.99 lakh, it hits 100 in just 8 seconds.",'
        '"cited_spec_names":["price_ex_showroom"]},'
        '{"role":"cta","text":"Would you buy one? Tell us below.","cited_spec_names":[]}'
        ']}'
    )
    check = (
        '[{"claim_text":"172 bhp","verdict":"supported","backing_spec_name":"power",'
        '"note":"matches spec"},'
        '{"claim_text":"Starting at Rs 12.99 lakh","verdict":"supported",'
        '"backing_spec_name":"price_ex_showroom","note":"matches spec"},'
        '{"claim_text":"hits 100 in just 8 seconds","verdict":"unsupported",'
        '"backing_spec_name":null,"note":"no 0-100 figure in the spec sheet"}]'
    )
    return MockLLMClient({
        "Write the Short script": draft,
        "Check the script": check,
    })


def run(llm: LLMClient) -> str:
    sheet = demo_spec_sheet()
    script = draft_script(sheet, llm)
    structural = structural_citation_check(script, sheet)
    report = fact_check(script, sheet, llm)
    return render_gate1_report(script, sheet, report, structural)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--real", action="store_true",
                        help="Use GeminiLLMClient instead of the mock demo.")
    args = parser.parse_args()
    llm: LLMClient = GeminiLLMClient() if args.real else _mock_with_planted_hallucination()
    print(run(llm))


if __name__ == "__main__":
    main()
