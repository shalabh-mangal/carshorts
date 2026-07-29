---
name: project-carshorts-roadmap-build
description: "Autonomy-core + AI-video build (2026-07-29): what shipped, where it lives, and the hard wall."
metadata:
  node_type: memory
  type: project
---

Owner gave full lead + approvals (2026‑07‑29) to build the roadmap to completion —
autonomy + a creative leap — with two standing limits kept: **never auto‑publish**
(Gate 2 is the owner's) and **no push to the remote** (local commits only). Shipped
in commit `d353589` on `main`, 169 tests green.

## Autonomy core (the system can now start a car on its own)
- **Feature‑claim guard** (`writing/draft.py:unsourced_features_check`) — flags a
  fabricated FEATURE ("cruise control", "sunroof") the number‑guard missed. Wired
  into `produce` + `writescript`; writer/editor prompts hardened too.
- **Write‑time length enforcement** (`draft.py:enforce_length`, `writescript`) —
  trims an overlong script (a Punch draft was ~196 words) below the ~120‑word cap
  before it fails the render's length QA.
- **Web fact + price research** (`sourcing/webresearch.py`, `carshorts research`) —
  the replacement for the thin Wikipedia crawl: pulls the FULL article text and a
  free LLM (GROQ) extracts rich SOURCED specs (each with a verbatim sentence) +
  a best‑effort DDG price search. Owner still CarDekho‑verifies at Gate 1. Wired
  into `pipeline.draft` so the heartbeat self‑serves facts for a new car.
- **Auto plate‑blur** (`quality/assetvet.py`) — a plated‑but‑good photo is now
  RECOVERED (Gemini plate‑box → blur → re‑vet CONFIRMS unreadable → keep) instead
  of quarantined. A still‑readable plate is never kept. Also fixed the Windows
  vet file‑lock (WinError 32 — image handles now close before move).

## Creative leap — AI video (car stays real; AI = comedy only)
- **LTX‑Video** runs on the **RTX 5060 8GB** in an ISOLATED **`.venv-video`** (its
  newer diffusers can't break chatterbox's pin). t2v + i2v, **~57s/clip at
  512×320**, peak VRAM ~9.55GB (spills to system RAM — works, a bit slow). Model
  is `Lightricks/LTX-Video` via diffusers; needs `tiktoken`.
- **`adapters/videogen.py`** — subprocess bridge to `tools/ltx_worker.py` (run by
  the video venv) + a provenance ledger (`data/gen_provenance.json`, gitignored):
  every generated clip is tagged `generated`.
- **`adapters/humor.py`** — reusable comedic‑cutaway library (rocket=turbo,
  money=value, shield=safety, mind‑blown=shock, boot=space); `joke_for(text)`
  maps a beat to a cached clip. Wired into `produce` as ONE flash on the **peak
  beat only** (`--humor`, default on when the video env exists).
- **THE WALL (sacred):** the car and every fact are ONLY ever REAL footage. t2v is
  comedy garnish, never the car; i2v (Living Stills) only animates a vetted photo.
  QA's opens/closes‑on‑subject‑car keeps the real car bookending; AI use gets
  disclosed. NEVER text‑to‑video the car itself.

## Still open (next)
- Wire **i2v Living Stills** into `produce` (animate the real car stills — the
  capability exists in videogen/worker; not yet inserted into the render).
- AI‑clip quality is lo‑fi/janky at 8GB (fine for a 0.5–1s flash); tune steps/res
  and consider portrait dims so clips fit the vertical frame without heavy crop.
- Price‑search is best‑effort (DDG can be blocked); owner adds price when missing.

Related: [[project_carshorts_free_stack_voice]] (voice finalized: chatterbox
`hype` 0.85/0.35, re‑roll gate, proportional pop marks) · [[project-carshorts-brain-gaps]]
· [[feedback_no_commit_without_permission]] (broad approval given for this build).
