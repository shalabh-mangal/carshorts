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

## Package structure (src/carshorts/, domain subpackages)
- `cli.py` — unified entrypoint: `carshorts <command>` (or `python -m carshorts <command>`); chdirs to the project root so paths resolve from anywhere
- `core/` — config, models, learnings, **paths** (canonical dir layout — one ROOT)
- `adapters/` — I/O boundaries: llm, tts, renderer, ffrenderer, ffoverlay, footage, stock, music, specsource
- `writing/` — prompts, draft, writescript, gate1
- `rendering/` — produce (phrase-sync render + QA loop), audiopolish, thumbnail
- `quality/` — qa, vqa, assetvet, firstframe
- `sourcing/` — crawl, newscrawl, ingest
- `intel/` — analytics, analyze, competitors, engagement, experiments, comments, retention_watch
- `agents/` — agent (headless claude harness), brain, rework, harness
- `orchestration/` — pipeline (queue), heartbeat (daily), calendar_plan
- `publishing/` — publish, publishkit, ytauth
- `portal/` — review-station FE (server + __main__)

Repo data dirs (all under `core.paths`): `charters/` role charters + `TASTE.md`
(the LAW; read by `agents/agent.py`), `data/scripts/` locked `.script.json` per
video, `specs/` + `specs_extras/` fact sheets, `assets/` licensed pool, `out/`
renders (gitignored), `context/manifests/` curated render-record mirror.
