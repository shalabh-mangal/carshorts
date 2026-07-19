# carshorts — Milestone 1 vertical slice

Proves the riskiest claim in the project before any video code exists:
*can the system produce a 60s car script where every factual claim is
traceable to a source, and a human can verify it in ~2 minutes?*

No video. No audio. No publishing. Just discover → script → **Gate 1**.

## Run it

```bash
pip install -e .                 # or: pip install pydantic
PYTHONPATH=src python -m carshorts.run
```

The default run uses a mock LLM with a **deliberately planted hallucination**
(a 0–100 time that isn't in the spec sheet) so you can watch Gate 1 catch it.

To run against a real free-tier model:

```bash
pip install -e ".[real]"
export GEMINI_API_KEY=...
PYTHONPATH=src python -m carshorts.run --real
```

## Test

```bash
pip install -e ".[dev]"
pytest
```

## The one idea that matters

Writing and fact-checking are **separate LLM calls**:

- The **writer** (`DRAFT_SYSTEM`) may use *only* the provided spec sheet — it
  cannot introduce a figure from its own memory.
- The **skeptic** (`FACTCHECK_SYSTEM`) runs as a separate pass over the finished
  script and flags any claim the spec sheet doesn't back. Its incentive is to
  doubt, not defend.
- A **structural check** (`structural_citation_check`) catches phantom citations
  with no LLM at all.

Gate 1 then shows the human the flags first, each real claim next to its source
sentence. That linkage is what makes verification fast.

## Layout

```
src/carshorts/
  models.py              typed contracts (DDD value objects)
  adapters/llm.py        LLMClient interface + Mock + Gemini impls
  prompts/templates.py   writer / skeptic / ranker prompts
  stages/pipeline.py     rank, draft, fact_check, structural check
  gate1.py               human review report renderer
  run.py                 CLI entry point
tests/test_pipeline.py   accuracy behaviours, all LLM mocked
```

## Deliberately NOT here (premature for this milestone)

Video, TTS, footage sourcing, publishing, web UI, SQLite persistence, Kafka,
Temporal, multi-agent orchestration, RAG, multi-domain plugins. Each attaches
later at a known seam.
