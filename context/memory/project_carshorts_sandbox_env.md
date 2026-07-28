---
name: project-carshorts-sandbox-env
description: "Claude's tools for carshorts run in a synced cloud sandbox, NOT the owner's desktop — installs/tasks don't reach the owner's machine."
metadata: 
  node_type: memory
  type: project
  originSessionId: faea6523-542d-47bc-ac54-9dd402f1cb21
  modified: 2026-07-24T12:52:27.714Z
---

Established 2026-07-24: Claude Code's tool execution for carshorts happens in a **cloud sandbox** (reports as machine `MANGALJIS-PREDA`, user `admin`) that **bidirectionally syncs the project folder** `D:\Personal Projects\carshorts` (code, `data/`, `assets/`, `.env`, `.git`) but is a **different machine from the owner's Windows desktop**. Proof: a file I installed (`C:\Users\Admin\AppData\Roaming\npm\claude.cmd`) exists and runs in the sandbox but `Test-Path` returns False on the owner's desktop.

**What syncs to the owner:** all project files + git commits.
**Sandbox-only (never reaches the owner's desktop):** system installs (`.venv`, ffmpeg via winget, Node + `claude` CLI) and anything registered with the OS — the `schtasks` daily tasks (`carshorts-heartbeat`, `carshorts-retention-watch`) and the `localhost:8787` portal (owner sees it only through the in-app browser pane).

**Consequences to remember:**
- "Upload daily, unattended" CANNOT rely on the sandbox — it's ephemeral. It must run on a persistent machine (owner's always-on desktop or a cloud VM). This is why a cross-platform setup script is being built ([[project-carshorts-brain-gaps]]).
- The agent layer's `claude` CLI in the sandbox can't use interactive `/login`; it needs a headless `ANTHROPIC_API_KEY` (which syncs via `.env`), and that's pay-per-token cost.
- I can still produce videos, run tests, and commit through the sandbox; artifacts + commits sync to the owner, who reviews via the portal. See [[project-carshorts-windows]].

Full tonight plan in the repo: `NEXT_SESSION_PLAN.md`.
