# carshorts — project guide for Claude Code

An AI platform that produces ~60-second YouTube Shorts about cars. This file is
the source of truth for *why* the project is shaped the way it is. Read it
before proposing architecture changes — several "obvious improvements" have
already been considered and deliberately rejected. They're listed below.

## Current state

**Milestone 1 (vertical slice) is built and passing.** It covers exactly:
discover → rank → draft script → fact-check → Gate 1 review report. No video,
no audio, no publishing, no web UI, no persistence. That narrowness is
intentional — the slice exists to prove one risky claim before any expensive
code is written.

Run the demo (offline, mocked LLM, deterministic):
```bash
pip install -e ".[dev]"
python -m carshorts.run        # prints a Gate 1 report; catches a planted hallucination
pytest                         # 5 tests, all LLM calls mocked
```

Run against a real model (needs a free Gemini API key in GEMINI_API_KEY):
```bash
pip install -e ".[real]"
python -m carshorts.run --real
```

## The one idea the whole product rests on

**Writing and fact-checking are SEPARATE LLM calls. Never merge them.**

- The **writer** (`DRAFT_SYSTEM` in `prompts/templates.py`) may use ONLY the
  facts in the supplied spec sheet. It is forbidden from introducing any
  number, price, or date from its own memory.
- The **skeptic** (`FACTCHECK_SYSTEM`) is a separate pass over the finished
  script + the same spec sheet. Its only job is to flag claims the sheet does
  not support. Its incentive is to doubt, not to defend.
- A **structural check** (`structural_citation_check`) catches citations
  pointing at nonexistent specs with no LLM at all.

If you ever find yourself writing a single prompt that both writes and
verifies, stop — that defeats the entire accuracy design. The model will bless
its own hallucinations.

## The five swappable adapters

Every external dependency sits behind an interface so it can be replaced without
touching pipeline logic. This is the *only* abstraction layer justified right
now (three concrete renderer implementations are foreseeable, so the seam is
real, not speculative):

- `LLMClient` — Gemini free tier now; Ollama/local or paid models later.
- `FootageSource` — the hard one. License-clean car footage is scarce, and this
  is a legal problem, not an AI problem. Not yet implemented (Milestone 2+).
- `TTSProvider` — free engine now, ElevenLabs-class when budget appears.
- `VideoRenderer` — stock-B-roll first; avatar and generative are v2/v3
  implementations of the SAME interface, A/B tested against real analytics, not
  guessed at upfront.
- `Publisher` — YouTube first; Instagram/Facebook are later implementations.

## Decisions already made — do NOT re-propose without a strong new reason

- **No Kafka, no Temporal, no microservices, no multi-agent orchestration, no
  RAG, no vector DB, no multi-domain plugin system.** All were in the original
  brief. All are premature at the real target: a few high-quality videos a day
  with a human in the loop. They attach later at the adapter seams when a
  concrete constraint demands them. Adding any of these now is over-engineering.
- **Two human gates, and Gate 1 is the quality firewall.** Gate 1 (verify specs
  before rendering) comes BEFORE any expensive step on purpose — never spend
  compute on a video built from a hallucinated figure. If automation ever
  removes a gate, it's Gate 2 (final watch), never Gate 1.
- **Python, single app, SQLite + local files when persistence is added.** The
  owner is strong in Java/Spring; Java is reserved for a possible later
  control-plane API, not the pipeline (the media/TTS/LLM ecosystem is
  Python-native). Do not split stacks in the MVP.
- **One content template first** (new-launch / single-car spotlight). Comparison
  is the hardest (two cars, synced spec data, side-by-side visuals) — last, not
  first.
- **Pydantic models are the typed contracts** crossing every stage boundary;
  treat them as DDD value objects. A `Spec` is never a bare number — it always
  carries its source URL and the exact source sentence. That linkage is what
  makes Gate 1 a 2-minute check.

## Open task — Milestone 1's true exit criterion (NOT yet done)

The demo proves the *mechanism*. It does NOT yet prove the *number* that decides
the whole "95% automated" ambition: **how often does a real model hallucinate a
spec?**

Next step: build a small harness that loads ~20 real spec sheets (JSON from a
folder) instead of the single hardcoded `demo_spec_sheet()`, runs each through
`--real`, and tallies: how many scripts had ≥1 unsupported claim, and how many
slipped past the LLM checker but were caught structurally (or not at all). That
flag-rate is the go/no-go signal. High rate → Gate 1 stays heavy and "95%
automated" is really "AI-assisted editor." Low rate → proceed to the render
slice. Do not start Milestone 2 (render/TTS) until this number exists and has
been reviewed.

Note on free-tier specifics (verified mid-2026, re-check before relying):
the free tier covers Flash / Flash-Lite models only; Pro is behind billing. Use
a current model string like `gemini-2.5-flash` (the `1.5`/`2.0` families are
retired). Newly created AI Studio keys are auth-restricted by default and work;
old unrestricted keys are rejected.

## Layout

```
src/carshorts/
  models.py              typed contracts (Spec carries its source!)
  adapters/llm.py        LLMClient interface + Mock + Gemini impls
  prompts/templates.py   writer / skeptic / ranker prompts
  stages/pipeline.py     rank, draft, fact_check, structural check
  gate1.py               human review report renderer
  run.py                 CLI entry point (--real for live model)
tests/test_pipeline.py   accuracy behaviours, all LLM mocked
```

## Working style the owner asked for

Act like a principal engineer reviewing a design, not a yes-man. If a proposed
change adds complexity the current milestone doesn't need, say so. Prefer
explaining the *why* over emitting code. Keep milestones sequential — finish and
review one before starting the next.
