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
the owner's OWN voice from `data/voice/owner_reference.wav` and speaks **English /
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

**Decision:** post‑render VQA (Gemini vision) is **advisory only** — it's noisy
(false‑positives on blurred plates, flags different frames each run). The hard
guards are per‑image `assetvet` + deterministic QA + the owner's eye.

Related: [[feedback_no_commit_without_permission]] · [[feedback_portal_top_notch]] ·
[[project_carshorts_windows]] · the `claude setup-token` path is NOT needed (free
models replace it).
