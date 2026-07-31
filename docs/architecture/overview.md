# Architecture Overview

CarShorts is the first implementation of an AI-native media OS: a self-correcting
factory that turns sourced facts + real footage into short vertical videos, with
two human gates (script approval, final watch). This doc is intentionally
lightweight — enough to orient a new contributor in ~30 minutes.

## Folder purpose (one responsibility each)

| Folder | Responsibility | Committed? |
|---|---|---|
| `src/carshorts/` | All source code (domain subpackages) | yes |
| `tests/` | Offline pytest suite | yes |
| `tools/` | Standalone helper scripts (e.g. LTX worker) | yes |
| `charters/` | Role charters + `TASTE.md` (the taste LAW) | yes |
| `specs/`, `specs_extras/` | Sourced fact sheets (per car) | yes |
| `assets/` | Curated, licensed media pool (real footage/stills, fonts, music) | yes |
| `knowledge/` | Human-tuned inputs: learnings, calendar, competitors, baselines, voice ref | yes |
| `context/` | Curated render-record manifests + notes | yes |
| `data/` | **Runtime state**: queue, recipes, reports, feedback, scripts, ledgers | yes (records) |
| `out/` | **Output**: rendered videos + publish kits | no (gitignored) |
| `workspace/` | **Generated/regenerable**: AI clips, voice cache, logs | no (gitignored) |

The key seam: **source/knowledge (committed inputs)** vs **runtime state
(machine-written records)** vs **output/workspace (regenerable artifacts)**.
Every path flows from `src/carshorts/core/paths.py` — the single source of truth
for the layout, so moving a directory is a one-file edit there.

## Module responsibilities (`src/carshorts/`)

| Package | Purpose | Key inputs → outputs |
|---|---|---|
| `core/` | Config, models, **paths**, learnings | — |
| `adapters/` | I/O boundaries: llm, tts, renderer, ffrenderer, ffoverlay, footage, stock, music, videogen, specsource | external services ↔ domain |
| `writing/` | prompts, draft, writescript, gate 1 | spec sheet → locked `.script.json` |
| `rendering/` | produce (phrase-sync render + QA loop), audiopolish, thumbnail | script + assets → `out/*.mp4` + manifest |
| `quality/` | qa, vqa, assetvet, firstframe | render/asset → pass/fail + fixes |
| `sourcing/` | crawl, newscrawl, ingest, webresearch | web/inbox → specs + vetted asset pool |
| `intel/` | analytics, analyze, competitors, engagement, experiments, comments, retention_watch | YouTube data → learnings |
| `agents/` | agent (headless claude), brain, rework, harness | state → bounded decisions |
| `orchestration/` | pipeline (queue), heartbeat (daily), calendar_plan | — → a drafted card |
| `publishing/` | publish, publishkit, ytauth | final → YouTube (owner gate) |
| `portal/` | review-station FE (Gate 1/2 as a product) | queue cards → owner decisions |

## Data flow (happy path)

```
sourcing (facts + footage)  →  writing (script)  →  [Gate 1: owner]
     →  rendering (produce + QA loop)  →  out/<slug>_draft.mp4
     →  [Gate 2: owner]  →  publishing (unlisted upload)
     →  intel (analytics → learnings → knowledge/learnings.json)  ↺
```

## Agent flow

Agents are **bounded**: they decide, explain, and queue — they never publish,
spend, or cross a human gate. `heartbeat` drives the daily cadence; `brain`
triages failures + writes strategy; `rework` acts on owner feedback. The two
gates (script approval, final watch) always belong to the owner (`charters/TASTE.md`).
