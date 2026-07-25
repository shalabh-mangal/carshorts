# Session handoff — for any Claude session picking up carshorts

**What this is:** distilled state from the 2026-07-22/23 build session
(supervisor session id f62839e4-65b7-407f-a5e2-f8ee7b449445; full raw
transcript at ~/.claude/projects/-Users-apple-Github-thrust/<id>.jsonl).

## Where things stand
- 2 videos live: Mahindra Thar (EXCHHyUDyyg), Hyundai Creta (NXa-7sG13Uw).
- Architecture: deterministic hands (produce/QA/VQA/portal/publish) +
  agentic minds (charters/*.md charters run headless via src/carshorts/agent.py,
  12 runs/day budget, journaled to data/agent_log.jsonl).
- Owner reviews at localhost:8787 (python -m carshorts.portal). Two-gate
  approval: draft approve -> premium final -> second approval -> publish.
- Channel voice: en-IN-NeerjaExpressiveNeural, rate +3% (drafts AND finals).
- Scheduled supervisor audit every 8h (Claude app scheduled task
  'carshorts-supervisor-audit') — heals, folds inbox, ships 1 improvement.

## Read these before acting (in order)
1. charters/TASTE.md — owner taste constitution + incident ledger. LAW.
2. ROADMAP.md — tier ladder; Tier 2 (analytics activation) is next.
3. data/learnings.json, data/brain_inbox.jsonl — live lessons + queued work.
4. Memory dir (if session runs from ~/Github/thrust it auto-loads):
   ~/.claude/projects/-Users-apple-Github-thrust/memory/

## Standing owner mandates
- Continuously self-improve without being asked (one improvement per shift).
- Ask before spending paid/scarce resources; free drafts, premium finals.
- Every feedback channel must either change the render or say why it can't.
- Verify by artifact (frames/files), never by config or agent say-so.

## Immediate next steps
- Tier 2: run analyze.py once videos have ~24h data; portal analytics tab.
- Curator follow-up: Hyundai press images + motion clips (last run timed out
  after the Wikimedia haul). VQA majority-vote fix queued in brain_inbox.
- Video #3: Tata Nexon (hype, five_things) — numbered-chips experiment queued.
