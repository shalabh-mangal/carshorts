# carshorts — agent context

Self-correcting YouTube Shorts factory (cars, India). README.md = how it works;
ROADMAP.md = what's next. Channel: carshorts (Nexon, Swift, Thar live).

## Non-negotiables (learned the hard way)
- Visuals MUST track narration phrase-by-phrase — the owner's #1 quality bar.
- Vet every asset by LOOKING at it (Pexels tags lie); plates blurred/excluded;
  NEVER third-party watermarked/ripped content — refuse, offer legal routes.
- Facts only from sourced sheets (specs/ + specs_extras/); prices are estimates
  from a one-off CarDekho/CarWale lookup — never automated scraping of them.
- Free tools for drafts; ElevenLabs only for finals (voice cached; ask before
  ANY paid spend — standing rule). Edge cases: cache keys include voice_id.
- Every render must end QA-green (12 checks) before the owner sees it.
- Gate 1 (script approval) and Gate 2 (final watch) belong to the owner. Always.

## Working style
- Verify by rendering + reading frames (grids via ffmpeg tile), not by assuming.
- New stock/CC fetches get a visual vet grid before entering the pool.
- specs come from `crawl` (generation-scoped) then VERIFIED against CarDekho.
- Run `pytest` (offline, 31 tests) before committing; CI runs it on push.

## Key modules
pipeline (orchestrator+queue) · writescript (variants→judge→editor) ·
produce (phrase-sync render + QA loop) · qa / vqa · audiopolish · publishkit ·
publish · analyze (retention→beat) · comments · calendar_plan · ingest ·
learnings · config (.env)
