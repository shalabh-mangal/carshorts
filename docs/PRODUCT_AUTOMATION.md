# carshorts — Product, Quality & Automation Plan (living doc)

**Owner:** Shalabh (taste + the two gates) · **Engine:** Claude (everything else).
**Cadence goal:** ship one high-quality car Short **every day**.
**Constraint:** 100% free / open-source. Reach is the binding constraint, not craft.

This doc is the north star. Every change should move at least one of the three
axes below. Update it when the plan changes; don't let us drift.

---

## Operating principle: the Portal is the single cockpit

The owner should **never touch the terminal, a file, or a flag.** Everything the
machine needs from the owner — and everything it hands back — flows through the
portal (http://localhost:8787). If the pipeline needs something (footage, a joke,
a price confirmation, a taste call), it **posts a prompt into the portal**; the
owner answers there; the machine continues. One screen, per car, start to publish.

---

## The daily flow (per car)

| # | Stage | Who | Where / How | Status |
|---|-------|-----|-------------|--------|
| 0 | Pick car + source & verify specs | machine | crawl → CarDekho-verify → `specs/<slug>.json` | ✅ automated |
| 1 | **Script — 3 options** | machine writes, **owner picks/mixes** (Gate 1) | portal `script_review`: beat-mixer + "generate more" | ✅ built |
| 2 | **Voice — 3 samples** | machine renders, **owner picks** | portal voice picker (`out/voice_options/<slug>_*.mp3`) | ✅ built |
| 3 | **Content drop** — owner's real footage + jokes | **owner uploads** | portal drop-zone → `assets/cars/<slug>/own/` + `data/content/<slug>.json` | 🔜 P1 (next build) |
| 4 | B-roll fetch + vet | machine | free stock/CC + assetvet + slow-mo shorts | ✅ automated |
| 5 | Render (script→voice→phrase-synced video) | machine | shot-plan, overlays, QA-green (no loops/drops) | ✅ automated + guarded |
| 6 | **Final watch** (Gate 2) → publish | **owner approves** | portal player → Approve/Publish | ✅ built |
| 7 | Poll comment + learn from retention | machine | auto poll comment; analytics → learnings → next script | ✅ automated |

Gates 1 and 6 are the owner's, always. Never auto-publish.

---

## Portal capability roadmap (phased, build in order)

- **P0 — Cockpit basics** ✅ script picker/mixer, voice picker, draft/final player,
  approve/rework, "generate more scripts", always-load-final fix.
- **P1 — Content drop** 🔜 *next.* A drop-zone on the card (after script+voice
  pick) where the owner drags in **car clips** (→ `assets/cars/<slug>/own/`, auto
  letterboxed to 1080×1920, slow-mo'd if too short) and **jokes/notes**
  (→ `data/content/<slug>.json`). Multipart upload handler + FE dropzone.
- **P2 — Owner-prompt surface.** A `needs` list on each card the pipeline can
  append to (`{id, kind, prompt, options?}`), rendered as actionable prompts:
  confirm price, "beat 3 has no matching clip — upload one?", pick a thumbnail.
  Owner answers in-portal; response written back; machine resumes. Replaces
  every "tell the owner in chat" with a portal ask.
- **P3 — One-click produce from the portal.** Lock script + voice + content →
  "Produce" button runs the full render in the background with live progress
  (already partly wired via `_spawn_worker`).
- **P4 — Auto-advance daily.** `pipeline --next` pulls tomorrow's car from the
  calendar, runs 0→5, and parks it at Gate 1 in the portal each morning
  (heartbeat/cron). Owner opens the portal to two decisions and a watch.

---

## Three improvement axes (running backlog)

### A. Product / reach (the binding constraint)
- Hinglish content layer (scripts + Devanagari captions + Hindi number-guard). *(candidate Sprint 1)*
- Title/thumbnail experiments; hook A/Bs from the calendar.
- Rivalry/comparison formats (Sierra vs Creta) — high engagement.

### B. Video quality
- Owner real footage > AI b-roll (P1 content drop makes this frictionless).
- Living Stills (LTX-Video) for motion from stills on the RTX 5060.
- Better opener brightness/colourfulness (feed-norm QA is still advisory).

### C. Automation / reliability
- ✅ QA now gates loops + dropped overlays (machine-enforced, not eyeballed).
- ✅ Portal always serves the freshest final.
- P2 owner-prompt surface = no more out-of-band asks.
- P3/P4 = hands-off daily cadence.

---

## Portal builder contract (script options)
The `script_review` beat-mixer has exactly **5 role slots: hook · spec · value ·
peak · cta**. Every `<slug>_opt*.script.json` must have **exactly one beat per
role** (5 beats). Two beats sharing a role (e.g. two `spec`) pile into that
slot's library and render as duplicates ("everything twice"). Pack multiple
facts into one beat via multiple `pops` instead of adding a second same-role
beat. (Direct-render scripts like `<slug>_built.script.json` may have more
beats — this contract is only for builder-facing option files.)

## Working discipline (how we avoid re-iteration)
- **Staged, per car:** finalize script → voice → then video. Never overwrite a
  locked script.
- **Never repeat/loop clips** (owner's #1 rule; QA-gated). Clips must be ≥ their
  beat length or they loop.
- **Every render QA-green before the owner sees it.** Facts only from sourced
  sheets. Never auto-publish.
- **Branches:** `main` = green trunk; `sprint-N/*` = code; `car/<slug>` = content.
  Disjoint trees → conflict-free parallel work. Small, frequent merges.
