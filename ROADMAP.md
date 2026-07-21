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

## Next
3. Retention-curve → beat mapping (learn WHICH second loses viewers)
4. Inbox auto-ingest (vet, plate-blur, cut, name — automatically)
5. Semantic asset index + cross-video freshness budget
6. Experiment scheduler (deliberate A/B across the calendar)
7. Comment mining → topics + reply drafts
8. Provider fallback chains, .env secrets, structured logging
9. CI: golden-manifest integration tests
10. Hinglish/Hindi re-issues of winning videos
