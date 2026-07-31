# Sprint 0 Report — Architecture Foundation & Repository Reorganization

**Scope:** infrastructure decoupling only. No business logic, prompts, agents, or
workflows were changed. The 169-test suite passed at every step (the "no behavior
change" proof). Delivered on branch `sprint-0-reorg` in 5 commits.

---

## 1. Repository tree — before vs after

### Before
```
carshorts/
├── assets/            # curated pool + AI-generated clips MIXED (assets/gen/) + inbox
├── charters/
├── context/
├── data/              # curated knowledge AND runtime state MIXED:
│                      #   learnings, calendar, competitors, news_sources,
│                      #   music_tags, firstframe_baseline, voice/  (knowledge)
│                      #   queue/, recipes/, reports/, feedback/, scripts/, logs/,
│                      #   *.jsonl ledgers, budgets, caches            (runtime)
├── out/               # renders + tts_cache/ + voice_options/
├── specs/  specs_extras/
├── src/carshorts/     # paths hardcoded as cwd-relative strings in ~25 modules
├── tests/
└── tools/
```

### After
```
carshorts/
├── src/carshorts/     # core/paths.py = single source of truth for the layout
├── tests/
├── tools/
├── docs/              # NEW
│   ├── SPRINT-0.md
│   └── architecture/  # overview.md + adr/0001-repository-layout.md
├── charters/
├── specs/  specs_extras/
├── assets/            # curated, licensed media ONLY (gen/ removed)
├── knowledge/         # NEW — curated human-tuned inputs (committed)
│   ├── learnings.json  calendar.json  competitors.json  news_sources.json
│   ├── music_tags.json  firstframe_baseline.json
│   └── voice/          (owner reference clip)
├── context/
├── data/              # runtime state ONLY (queue, recipes, reports, feedback,
│                      #   scripts, ledgers)
├── out/               # OUTPUT: renders + publish kits (gitignored)
└── workspace/         # NEW — generated/regenerable, gitignored
    ├── generated/     #   ← assets/gen/
    ├── cache/tts/     #   ← out/tts_cache/
    └── logs/          #   ← data/logs/
```

---

## 2. Files / directories moved

| From | To | Kind |
|---|---|---|
| `data/learnings.json` | `knowledge/learnings.json` | knowledge |
| `data/calendar.json` | `knowledge/calendar.json` | knowledge |
| `data/competitors.json` | `knowledge/competitors.json` | knowledge |
| `data/news_sources.json` | `knowledge/news_sources.json` | knowledge |
| `data/music_tags.json` | `knowledge/music_tags.json` | knowledge |
| `data/firstframe_baseline.json` | `knowledge/firstframe_baseline.json` | knowledge |
| `data/voice/` | `knowledge/voice/` | knowledge |
| `assets/gen/` | `workspace/generated/` | generated |
| `out/tts_cache/` | `workspace/cache/tts/` | generated |
| `data/logs/` | `workspace/logs/` | generated |

Not a move but the foundation: ~40 hardcoded path literals across ~25 modules were
routed through `core/paths.py` (constants first pointed at the *old* locations, so
the physical moves above were then a one-file `paths.py` edit).

---

## 3. Structural decisions

1. **Single path source of truth** (`core/paths.py`), grouped by responsibility:
   KNOWLEDGE / RUNTIME / OUTPUT / WORKSPACE. Moving a directory = one edit.
2. **Three-way separation:** committed inputs (`knowledge/`, `assets/`, `specs/`) vs
   machine-written runtime records (`data/`) vs regenerable artifacts
   (`out/`, `workspace/`, both gitignored).
3. **Paths-first migration** so every step kept tests green (behavior identical).
4. **`out/` deliberately NOT moved** — live queue cards store `out/...` paths;
   relocation needs a card-path migration (deferred to Sprint 1).

---

## 4. ADRs created

- `docs/architecture/adr/0001-repository-layout.md` — the source/knowledge/runtime/
  output/workspace decision, context, and consequences.

(Plus `docs/architecture/overview.md` and `docs/SPRINT-0.md`.)

---

## 5. Remaining technical debt

- **`out/` still lives in the repo root**, not under `workspace/` — the one
  generated dir not yet relocated (blocked on a card-path migration).
- **`data/` still holds committed runtime records** (queue, recipes, scripts,
  jsonl ledgers). Whether the pure-ephemera ledgers should become gitignored
  workspace is undecided.
- **A few modules capture `X = paths.X` at import** rather than reading `paths.X`
  at call time. One such capture (firstframe's baseline) caused a test-order bug
  that was fixed this sprint; the rest remain a latent fragility.
- **Automotive-specific knowledge is spread across `writing/` + `sourcing/`** with
  no explicit domain boundary — fine today, friction for a second vertical.
- Minor: an intermediate commit incidentally added the `assets/cars/test-car/`
  fixture images (previously untracked); harmless, and useful for CI.

---

## 6. Risks & compromises

- **Compromise (Principle 1 — don't break working software):** `out/` left in
  place. The alternative (move + migrate card paths) risked breaking the running
  portal and the just-published Sonet's references for little immediate gain.
- **Judgment call:** the `knowledge/` vs `data/` boundary is a reasonable reading
  of "curated vs machine-written", not a forced rule. `firstframe_baseline.json`
  (machine-built but stable) was placed in `knowledge/`; a reviewer could argue
  either way.
- **Low risk overall:** all moved dirs except the knowledge files are gitignored +
  regenerable, and nothing stores references to them (paths resolved at runtime).
  The 169-test suite is the guardrail and stayed green throughout.

---

## 7. Recommendations for Sprint 1 (NOT implemented)

Ranked by impact:

1. **Relocate `out/` → `workspace/renders/`** with a one-time migration of stored
   `out/...` paths in queue cards (+ `paths.resolve()` back-compat). Completes the
   "generated media has one home" goal.
2. **Add `CARSHORTS_WORKSPACE` env override** so the large regenerable tree can
   live on a separate disk (paths already honor `CARSHORTS_ROOT`).
3. **Decide per-file whether `data/` ephemera stays version-controlled;** move pure
   caches/ledgers to `workspace/` if not.
4. **Convert remaining import-time `X = paths.X` captures to call-time reads** to
   remove the last import-order fragility.
5. **Introduce a `domains/automotive/` boundary** for car-specific knowledge, so a
   second media vertical can slot in without touching `writing/`/`sourcing/`.

**Status: Sprint 0 complete. Stopping here — no Sprint 1 work started.**
