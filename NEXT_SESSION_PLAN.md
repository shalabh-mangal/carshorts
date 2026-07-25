# Next session plan — prepared 2026-07-24, execute ~9 PM

Owner is near a token limit; the heavy work is deliberately held. This file is
everything needed to run tonight fast. It syncs to the owner's desktop.

## 1. Environment reality (READ FIRST — this reframes "daily")
Claude's tools run in a CLOUD SANDBOX (machine MANGALJIS-PREDA, user admin) that
**syncs the project folder** `D:\Personal Projects\carshorts` (code, data/,
assets/, .env, .git) but is **a different machine from the owner's desktop.**
Confirmed: `C:\Users\Admin\AppData\Roaming\npm\claude.cmd` exists+runs in the
sandbox, returns False on the owner's desktop.

- **Synced to the owner:** all project files + git commits.
- **Sandbox-only (NOT on the owner's desktop):** the `.venv`, ffmpeg (winget),
  Node + `claude` CLI, the two scheduled tasks (`carshorts-heartbeat`,
  `carshorts-retention-watch`), and the portal at localhost:8787 (owner sees it
  only via the in-app browser pane).
- **Implication:** "upload daily, unattended" must run on a PERSISTENT machine —
  the owner's always-on desktop or a cloud VM — NOT this ephemeral sandbox.
  That is exactly what the setup script (task A) is for.

## 2. What the owner needs to decide/bring tonight
1. **Agent auth:** provide `ANTHROPIC_API_KEY` in `.env` (syncs) to enable the
   scriptwright/curator agents — pay-per-token Anthropic billing, budget-capped
   12 runs/day. OR keep the template-writer path (no agents). The sandbox cannot
   use an interactive `/login`; a headless key is the only option here.
2. **Next-video car:** Nexon five_things (verified specs, documented next) is the
   recommendation; or name another VERIFIED car. NOT Brezza (see §4).
3. **Where the system runs daily:** owner's always-on desktop, or a cloud VM.

## 3. Execution plan (ordered — all four workstreams the owner asked for)

### A. Setup script — caters to ALL setup cases incl. a NEW laptop
Deliver `tools/setup.ps1` (Windows) + `tools/setup.sh` (macOS/Linux) + `SETUP.md`.
Requirements:
- Detect OS/arch. Install: Python 3.12, ffmpeg, Node LTS, `@anthropic-ai/claude-code`
  (winget on Windows; brew/apt/dnf elsewhere). Skip anything already present.
- Create `.venv`, `pip install -e ".[dev,video,crawl,publish,real]"`.
- Set `PYTHONUTF8=1` persistently (the ₹/cp1252 fix) + ensure ffmpeg on PATH.
- Register the daily tasks: schtasks (Windows) / launchd (macOS) / cron (Linux),
  each wrapper OS-correct.
- IDEMPOTENT + verifies each step + prints a clear "owner to-do" (auth, which
  files to drop in). Non-zero exit on a hard failure.
- NEW-LAPTOP path documented in SETUP.md: `git clone` → run setup → drop in
  `.env`, `client_secret.json`, `youtube_token.json`, and the `assets/` pool →
  `python -m carshorts.heartbeat --status` to confirm.
- Run `pytest -q` + `ruff check .` at the end as a smoke test.

### B. Next video (sandbox can do this now)
Produce the chosen car (default: Nexon `five_things`) from VERIFIED specs → draft
render (ffmpeg fast path, edge TTS, vetted opener) → queue card → owner Gate 1 in
the portal. If agents are enabled (task C), scriptwright verifies+writes; else the
template writer (`--no-agent`, GROQ) does.

### C. Agents via API key
- Wire `agent.py` to load `.env` and pass `ANTHROPIC_API_KEY` into the `claude`
  subprocess env (it currently relies on ambient auth). Add a test.
- Verify a trivial headless run returns a real answer, then a real scriptwright
  run on a new car (crawl+verify specs, write script through the guards).

### D. Portal (#3)
- Add an analytics tab to `portal.py`: per-video views/retention/CTR + the
  beat-drop map (join recipe cards + analytics/retention_log). Keep it
  stdlib/single-file, matching the existing review-station style. UX polish.

## 4. State snapshot (2026-07-24)
- Branch `feat/brain-organs`, NOT pushed, main untouched. Commits: 226f569
  (brain organs), c2f36a9 (quarantine 7 bad stills), 92bbfc1 (hybrid ffmpeg
  base), 528360e (ffmpeg overlays, fast path default-on), aa2399a (ruff + CI).
- **Uncommitted (working tree):** `agent.py` hardening (graceful when `claude`
  absent/unauthed) + a ROADMAP agent-layer note + this file. Ask before commit.
- All six brain organs built; **156 tests + `ruff check .` clean**; ffmpeg fast
  path ON by default (~3x faster, overlays verified pixel-identical).
- Open debt (ROADMAP): explicit `encoding="utf-8"` on all file I/O (mitigated by
  PYTHONUTF8); migrate EOL `google.generativeai` → `google.genai`.
- **Brezza specs are WRONG** (66 kW / 200 N⋅m / 1200 cc / "1.3-litre" —
  internally inconsistent, not the real 1.5L Brezza). Do NOT produce Brezza
  until the owner verifies specs against CarDekho.
- Channel state: 5 uploads, 767 views, 1 sub. Reach is the binding constraint —
  the experiment ledger can't conclude until videos clear ~500 views. Cadence
  stopped after 2026-07-22.
- Also: delete the stray `env` secrets file (duplicate of `.env`, now gitignored).
