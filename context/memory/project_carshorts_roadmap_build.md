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

## Living Stills WIRED (2026-07-30, commit 98cb204)
`carshorts liven <car>` pre-generates i2v clips for the car's vetted photos into
`own/` (gitignored, regenerable); produce prefers them and drops the matching
static still, and the opener falls back to a subject MOTION clip so the car opens
+ closes on animated real footage. Humor now inserts up to 3 VARIED flashes per
video (joke_for(avoid=) → next unused concept). Validated on Punch, QA-green.

## Voice numbers + HQ Living Stills + heartbeat self-enhance (2026-07-30, commit 531bbf3)
- **Numbers finally clean.** `tts._speak_numbers` speaks digits as words; the
  slur fix that made it land: drop British "and", COMMA-PAD multi-word numbers so
  chatterbox pauses/enunciates ("one hundred seventy," not a mushy "7070"), and
  spell acronyms it mangles (SUV→S-U-V, NCAP→N-cap). Whisper now hears clean
  digits (118, 1.2, 170, 5.59, 366) where it heard garbage.
- **THE cache trap (cost 2 wasted re-renders):** produce's TTS cache keyed on the
  RAW script line, so a voice-logic change silently reused stale audio — the
  transcript was byte-identical across "re-renders". Fixed: key on the SPOKEN text
  `_speak_numbers(normalize_for_speech(seg.text))`, so any speech-norm change
  self-busts. When a voice fix "doesn't take", suspect this cache first.
- **HQ Living Stills config VALIDATED** on the RTX 5060 8GB: **448×256, 73 frames
  @ 24fps (~3.0s), 40 steps** → smooth dolly push-in, stable, NO warp (the old
  384×224×25×20 was the janky version). Locked in `liven._HQ`; comedy flashes stay
  on the fast lo-fi default. Prompt = MOTION + quality bar only (car identity comes
  from the anchor photo). ~5 min/clip, pre-gen overnight so renders never wait.
- **Heartbeat self-enhances** (`heartbeat._ai_enhance`): at the END of a successful
  daily draft it ensures the joke library, livens THAT car's stills at HQ, and
  re-renders so the Gate-1 draft carries humor + Living Stills. No-op without
  `.venv-video`; never breaks the day.

## Still open (next)
- **Thin visual pool** is now the #1 gap: Punch has only ~4 assets (2 Living
  Stills + a generic speedo stock + a wintry NON-Indian forest dashcam), so the
  middle repeats and looks off-brand. Biggest quality lever = fetch + vet more
  REAL Punch b-roll (or more stills to liven). QA passes but variety is weak.
- Minor clone slips remain on normal words ("kicker"→"KIGA", "Nexon or"→"Next on
  our") — within re-roll recall tolerance; owner judges by ear at Gate 1.
- Price‑search is best‑effort (DDG can be blocked); owner adds price when missing.
- Consider PORTRAIT i2v dims so Living Stills fit the vertical frame without crop.

Related: [[project_carshorts_free_stack_voice]] (voice finalized: chatterbox
`hype` 0.85/0.35, re‑roll gate, proportional pop marks) · [[project-carshorts-brain-gaps]]
· [[feedback_no_commit_without_permission]] (broad approval given for this build).
