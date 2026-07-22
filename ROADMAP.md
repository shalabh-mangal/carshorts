# carshorts — system roadmap

Goal: a self-correcting, continuously-learning Shorts factory where the human
does taste (script approval, final watch, footage) and the system does the rest.

## Done
- Fact machine: sourced specs + news, skeptic, number-guard, structural check
- Script studio: variants → judge → editor; personas; formats; learnings injected
- Render: phrase-synced cuts (TTS word marks), speech-timed overlays, motion
  variety, loop-close, mood-matched music, ducked/limited/-14 LUFS audio,
  unified grade, keyword + callout cards
- QA gate (12 checks) + auto-fix loop + failure journal + auto-lessons
- Publish: kit (title-promise check), API upload, thumbnail, recipe linkage
- Learning: recipe cards, analytics join (analyze.py), learnings injection

## In progress
1. **Visual QA** — the system sees its own frames: per-cut frame vs phrase via
   vision model; flags plates, watermarks, wrong vehicles, mismatches.
2. **Orchestrator** — pipeline.py: one command per car through draft + QA, then
   an approval queue (Gate 1 human), `--approve` runs final + upload.

## Done (cont.)
3. Retention-curve → beat mapping ✅
4. Inbox auto-ingest ✅
8. .env secrets + provider fallback chains ✅

## Next (agreed 2026-07-21, execute in order, auto-advance)
A. **Hardening sprint ✅** — golden-manifest integration tests (mock TTS +
   --plan-only), GitHub Actions CI. produce.py refactor: incremental, behind
   the held tests, as modules get touched (not big-bang).
B. **Experiment scheduler ✅** — data/calendar.json of pre-assigned A/Bs
   (persona / hook-type / format / length / music rotations);
   `pipeline --next` pulls the top entry. Makes learnings causal.
C. Comment mining ✅ (comments.py — topics to data/topic_ideas.json, draft replies; re-run as audience grows)
D. **Brain v1 (in progress)** — brain.py: embedded judgment (failure triage
   beyond the fix-table, asset-vet second opinion, news curation, weekly
   strategy note) with decisions journal (data/brain_log.jsonl). Groq for
   bounded verdicts; headless Claude for hard calls. Daily heartbeat via cron.
E. **Review portal v1 (in progress)** — portal.py (localhost, stdlib): daily
   draft variants side by side, BEAT-LEVEL feedback framework (tag hook/visual/
   pacing/joke per section), pick → rework → approve → auto-upload → analytics
   tab. Feedback JSON feeds learnings. v2: variants differ by one calendar
   variable; unlisted-upload mobile review.
F. Semantic asset index + cross-video freshness (as footage grows)
G. Hinglish/Hindi re-issues of winners
H. Cadence: daily heartbeat — brain drafts, you approve


## North star (owner directive, 2026-07-22): a system with its own brain

Architecture: **deterministic hands, agentic minds.** The tested pipeline
(produce/QA/VQA/portal/publish) stays the hands. Five Claude-powered minds
(headless `claude -p`, role charters in agents/, budget-capped, journaled)
supply the judgment. The interactive supervisor (Claude) audits, corrects,
and grows the free brain's menu from every escalation.

- [x] **P1 Foundation** — agent harness (src/carshorts/agent.py: budget
      12 runs/day, 40-turn cap, journal data/agent_log.jsonl), mechanic +
      supervisor charters, rework dead-ends escalate to the mechanic,
      menu-growth inbox (data/brain_inbox.jsonl). Smoke-tested live.
- [ ] **P2 Scriptwright** — agents/scriptwright.md: crawl fresh news +
      price/spec data from outlets (free/official), write the script with
      humor that lands + curated pops; output = specs_extras + script JSON
      through the existing number-guard/fact-check gates.
- [ ] **P3 Analyst** — agents/analyst.md: weekly competitor tactic research
      (what top car channels do for attention/retention) + own analytics
      (retention curve → beats) → learnings + experiment calendar entries.
- [ ] **P4 Composer** — agents/composer.md: car personality profile →
      music mood/beat/SFX choices (extends music_tags.json + generate_beat).
- [ ] **P5 Curator** — agents/curator.md: crawl assets (Wikimedia, official
      press kits, Pexels) with license checks, build per-car pools, propose
      stitching variety (shot plans) for the renderer.
- [ ] **P6 Supervisor cadence** — scheduled daily supervisor run (audit
      agent logs, fold brain_inbox into the free menu, heal stuck cards,
      report to owner). Needs owner OK for the schedule mechanism.
