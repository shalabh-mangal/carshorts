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
D. Semantic asset index + cross-video freshness (as footage grows)
E. Hinglish/Hindi re-issues of winners
F. Cadence: aim daily once A+B land — the loop learns per upload
