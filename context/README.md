# Context architecture — every layer of the system's knowledge

Who reads what, and when. Fresh Claude session: read SESSION_HANDOFF.md
(repo root) first, then follow this map.

## Layer 1 — LAW (read before any work)
- `charters/TASTE.md` — owner taste constitution + incident ledger. Read by
  every agent charter as a hard first action. Owner rules never deleted.

## Layer 2 — Live operational state (machine-written, committed)
- `data/learnings.json` — max 12 active lessons, injected into writer prompts
- `data/brain_inbox.jsonl` — queued proposals/directions; folded each audit
- `data/agent_log.jsonl` / `data/agent_budget.json` — agent journal + budget
- `data/calendar.json` — experiment schedule (`pipeline --next` consumes)
- `data/sound_profiles/` — composer's per-car sound personality
- `data/supervisor_reports/` — 8-hourly shift reports

## Layer 3 — Role charters (`charters/*.md`)
scriptwright, curator, composer, analyst, mechanic, supervisor.
All open with the TASTE.md law + self-verification duty.

## Layer 4 — Supervisor memory mirror (`context/memory/`)
Carshorts-relevant snapshot of the interactive supervisor's persistent
memory (working-style preferences + the project log). Source of truth
lives outside the repo and auto-loads for supervisor sessions; this
mirror lets ANY session read it. Unrelated/private memories are
deliberately NOT mirrored.

## Layer 5 — History
- `SESSION_HANDOFF.md` (root) — distilled founding-session state
- Git log — every decision narrated in commit messages
- `ROADMAP.md` — tier ladder, done/next
