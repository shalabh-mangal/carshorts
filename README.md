# carshorts — a self-correcting YouTube Shorts factory for cars

Turns a car name into a published, fact-checked, phrase-synced YouTube Short —
free tools for drafts, one premium voice call for finals, human judgment at
exactly two gates.

## The two commands that matter

```bash
python -m carshorts.orchestration.pipeline "Hyundai Creta"          # or: pipeline --next (calendar)
#  → script (variants→judge→editor) → free draft render → QA + Visual QA
#  → approval card in data/queue/            ← GATE 1: watch it, edit the script
python -m carshorts.orchestration.pipeline --approve hyundai-creta
#  → ElevenLabs final → publish kit → uploaded public → recipe linked
```

## What the machine guarantees per video
- **Facts**: every number sourced (spec sheet + news with URLs); separate LLM
  skeptic + deterministic number-guard; prices labeled as estimates.
- **Sync**: cuts land where the words do (TTS word timestamps → phrase-matched
  visuals, 0.15s b-roll lead); on-screen text appears with its words.
- **Legality**: own/CC/press/vetted-stock assets only; plates blurred; no
  third-party watermarks, ever.
- **Craft**: curiosity hook ≤2.5s, ≤63s runtime, no repeated asset, car on the
  first and last frame, ducked music at −14 LUFS, loop-close ending.
- **Verification**: 12-check QA gate (auto-fix loop) + vision QA on real frames;
  failures journaled and turned into standing lessons.

## The learning loop
`data/recipes/` (every creative choice) + YouTube Analytics (`analyze.py`,
retention curve mapped to beats) + comments (`comments.py` → topic ideas) feed
`data/learnings.json`, which is injected into every future script. The
experiment calendar (`calendar_plan.py`) pre-assigns A/Bs so cohorts compare.

## Layout
```
src/carshorts/       code (adapters/ prompts/ stages/ + one module per stage)
specs/ specs_extras/ verified spec sheets + human-curated price/news/value
data/scripts/             locked .script.json per video
assets/              inbox/ (drop footage) music/ (drop tracks) cars/<slug>/ stock/
data/                learnings, recipes, calendar, queue, reports, failures
out/                 renders, manifests, thumbs, publish kits, tts_cache
```

## Setup
`pip install -e ".[dev,video,real,crawl]"` · keys in `.env` (see `.env.example`)
· YouTube OAuth: `client_secret.json` + first run consents · `pytest` (offline).

See ROADMAP.md for what's next. Human gates are the product: keep them.
