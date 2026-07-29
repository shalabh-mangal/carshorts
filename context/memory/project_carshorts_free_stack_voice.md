---
name: project_carshorts_free_stack_voice
description: carshorts is now a 100% free/open stack; cloned multilingual voice shipped; moving to a new laptop.
metadata: 
  node_type: memory
  type: project
  originSessionId: faea6523-542d-47bc-ac54-9dd402f1cb21
  modified: 2026-07-28T06:35:41.338Z
---

carshorts pivoted to a **fully free / open‑source stack** — the owner does not
want to spend money (no API top‑ups, no ElevenLabs). What runs the pipeline:
GROQ/Gemini **free** LLMs, free stills (Wikimedia broadened+throttled + Openverse),
Gemini‑free vision vetting, and voice = edge OR the new **cloned voice**.

**Voice leap (2026‑07‑28):** `ChatterboxTTSProvider` (in `adapters/tts.py`) clones
the owner's OWN voice from `data/voice/owner_reference.mp3` and speaks **English /
Hindi / Hinglish** (Chatterbox multilingual, 23 langs). Enable with
`CARSHORTS_VOICE_ENGINE=chatterbox` in `.env`. Phrase‑sync marks via faster‑whisper
(proportional fallback). Owner plans to **move to Hinglish videos** — voice is
ready; remaining Hinglish work is the content layer (Devanagari captions/fonts,
Hindi scripts, fact‑guard). See `NEW_LAPTOP.md` + `ROADMAP.md` in the repo.

**New laptop (~2026‑07‑29):** ASUS TUF F16, i7‑14650HX, **RTX 5060 8GB**, 16GB RAM —
now the real host (replaces the ephemeral sandbox, [[project_carshorts_sandbox_env]]).
Great for the voice; entry‑tier for the image‑to‑video "Living Stills" leap
(LTX‑Video). Setup: `tools/setup.ps1` installs the `[voice]` extra + CUDA torch
(cu128 for Blackwell). Secrets (`.env`, `client_secret.json`, `youtube_token.json`)
are gitignored — copy them to the new machine by hand.

**Proven on the new laptop (2026‑07‑29):** the cloned voice RUNS on the RTX 5060 —
chatterbox 0.1.7 works fine on **torch 2.11.0+cu128** (its `torch==2.6` pin is
cosmetic; install voice extra first, then override with the cu128 wheel). Synth
**~8s/line warm** (first run ~8min: one‑time model downloads to ~/.cache/huggingface).
faster‑whisper word‑marks + Perth watermark both active. English AND Hinglish both
synthesize in the owner's voice. Enable via `CARSHORTS_VOICE_ENGINE=chatterbox`.

**Voice FINALIZED (2026‑07‑29, owner‑approved):** channel voice = Chatterbox clone,
persona **`hype` = exaggeration 0.85 / cfg_weight 0.35**, reference
`data/voice/owner_reference.mp3` (owner replaced the old .wav). **AVOID neutral
`(0.5, 0.5)`** — with this reference it drifts into a foreign ("Russian") accent;
the faithful zone is exaggeration ~0.85 + **cfg ~0.35** (counter‑intuitively, lower
cfg is TRUER to the reference here). Audition clips with
`tools/say.py "line" [--language hindi] [--exaggeration X --cfg Y]` (added 2026‑07‑29).
Note: owner explored ElevenLabs library voices (free previews) but we did NOT use them —
cloning a real creator's licensed voice = the same "no ripped content" line we hold on stills.

**Decision:** post‑render VQA (Gemini vision) is **advisory only** — it's noisy
(false‑positives on blurred plates, flags different frames each run). The hard
guards are per‑image `assetvet` + deterministic QA + the owner's eye.

Related: [[feedback_no_commit_without_permission]] · [[feedback_portal_top_notch]] ·
[[project_carshorts_windows]] · the `claude setup-token` path is NOT needed (free
models replace it).
