# ADR 0001 — Repository layout: source / knowledge / runtime / output / workspace

- Status: Accepted
- Date: 2026-07-31
- Context: AI Media OS Sprint 0 (infrastructure decoupling; no behavior change)

## Context

The repo mixed source code, human-curated inputs, machine-written runtime state,
and generated media in the same trees (`data/` held both the tuned `learnings.json`
and churning `queue/` cards; AI clips lived under the curated `assets/` pool).
Paths were hardcoded as cwd-relative strings across ~25 modules, so the layout was
implicit and a directory could not be moved without editing many files.

## Decision

1. **One source of truth for paths.** Every module reads its paths from
   `core/paths.py`, grouped by responsibility (KNOWLEDGE / RUNTIME / OUTPUT /
   WORKSPACE). Moving a directory is now a one-line edit there.

2. **Separate by responsibility:**
   - `knowledge/` — human-tuned inputs (learnings, calendar, competitors, voice
     reference, baselines). Committed. Was scattered under `data/`.
   - `data/` — machine-written **runtime state** (queue, recipes, reports,
     feedback, scripts, ledgers). Committed as operational records.
   - `out/` — **output** deliverables (renders, publish kits). Gitignored.
   - `workspace/` — **generated/regenerable** artifacts (AI clips, voice cache,
     logs). Gitignored, kept out of the source tree.

3. **Preserve working software (Principle 1).** Constants first pointed at the
   *current* locations (behavior identical, tests green), then directories moved.
   `out/` was NOT relocated because live queue cards store `out/...` paths;
   moving it needs a card-path migration (see future recommendations).

## Consequences

- New contributors can reason about the layout from `paths.py` + `docs/architecture`.
- Generated media no longer pollutes the curated `assets/` pool.
- The 169-test suite passed unchanged at every step (the "no behavior change" proof).
- Trade-off: `data/` still holds committed runtime records; whether those become
  workspace (gitignored) is deferred, not decided here.
