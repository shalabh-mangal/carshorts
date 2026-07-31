# AI Media OS — Sprint 0 Report

**Objective:** transform the repo from a working application into a maintainable
platform — separation of concerns, a single path source of truth, generated media
given a home — **with zero behavior change**. No business logic, prompts, agents,
or workflows were touched. The 169-test suite passed at every step.

## 1. Repository tree (after)

```
carshorts/
├── src/carshorts/         # all source (core, adapters, writing, rendering,
│                          #   quality, sourcing, intel, agents, orchestration,
│                          #   publishing, portal)  — core/paths.py = layout SoT
├── tests/                 # offline pytest suite (169)
├── tools/                 # standalone helpers (ltx_worker, …)
├── docs/
│   ├── SPRINT-0.md        # this report
│   └── architecture/      # overview.md + adr/0001-repository-layout.md
├── charters/              # role charters + TASTE.md (the LAW)
├── specs/ specs_extras/   # sourced fact sheets
├── assets/                # curated, licensed media pool (real footage/stills)
├── knowledge/             # NEW: human-tuned inputs (learnings, calendar,
│                          #   competitors, baselines, voice reference)
├── context/               # curated render-record manifests
├── data/                  # runtime state (queue, recipes, reports, feedback,
│                          #   scripts, ledgers)
├── out/                   # OUTPUT: renders + publish kits (gitignored)
└── workspace/             # NEW: generated/regenerable (gitignored)
    ├── generated/         #   ← was assets/gen/  (AI clips)
    ├── cache/tts/         #   ← was out/tts_cache/
    └── logs/              #   ← was data/logs/
```

## 2. Migration summary

| Change | From → To | Why | Compatibility |
|---|---|---|---|
| Centralize paths | ~40 hardcoded literals across ~25 modules → `core.paths` | one source of truth; move-a-dir = one edit | none — constants first pointed at current locations |
| Knowledge split | `data/{learnings,calendar,competitors,news_sources,music_tags,firstframe_baseline,voice,sound_profiles}` → `knowledge/` | separate curated inputs from runtime state | committed; paths repointed |
| Generated → workspace | `assets/gen/`→`workspace/generated/`, `out/tts_cache/`→`workspace/cache/tts/`, `data/logs/`→`workspace/logs/` | keep generated media out of the source/asset trees | all gitignored + regenerable; no stored references |
| `out/` kept in place | (unchanged) | live queue cards store `out/...` paths | avoided a breaking card-path migration |

**Fixes surfaced by the reorg (correctness, not new features):**
- `firstframe.load_baseline()` now reads the baseline path at call time, not via
  an import-time constant — this removed a test-order pollution bug.
- The golden-manifest test fixture re-roots every `core.paths` constant onto its
  tmp tree, so it tests fixture assets instead of the real repo.

## 3. Architecture notes

See [`architecture/overview.md`](architecture/overview.md) (folder purpose, module
responsibilities, data flow, agent flow) and
[`architecture/adr/0001-repository-layout.md`](architecture/adr/0001-repository-layout.md).
The seam is **source/knowledge (committed inputs)** vs **runtime state (records)**
vs **output/workspace (regenerable)**, all anchored in `core/paths.py`.

## 4. Future recommendations (ranked by impact — NOT implemented)

1. **Relocate `out/` → `workspace/renders/` with a card-path migration.** The last
   generated dir still in the root. Needs a one-time migration of stored
   `out/...` paths in queue cards + `paths.resolve()` back-compat. Highest impact
   on the "generated media has one home" goal; deferred only to avoid breaking
   live cards.
2. **Config surface for `CARSHORTS_ROOT`/workspace location.** Paths already honor
   `CARSHORTS_ROOT`; add an optional `CARSHORTS_WORKSPACE` so deployments can put
   the large regenerable tree on a different disk.
3. **Split `data/` runtime further** into records (queue, recipes, scripts —
   worth keeping) vs pure ephemera (jsonl ledgers, caches → could become
   workspace). Decide per-file whether it belongs in version control.
4. **Reference `paths.X` at call time everywhere** (not `X = paths.X` module
   constants). A handful of modules still capture at import; converting them
   removes the last import-order fragility (one such bug was fixed this sprint).
5. **Make the domain seam explicit for multi-vertical.** Automotive-specific
   knowledge (car families, spec names) is spread across `writing/` + `sourcing/`;
   a `domains/automotive/` boundary would let a second vertical slot in cleanly.
   Larger than Sprint 0; a Sprint N item.

## Success criteria — met

- ✅ Behaves exactly as before (169 tests green throughout; no logic touched).
- ✅ Source clearly separated from runtime artifacts and generated media.
- ✅ Generated media has a dedicated home (`workspace/`).
- ✅ Single path source of truth (`core/paths.py`); zero hardcoded literals in src.
- ✅ No unnecessary abstractions introduced.
