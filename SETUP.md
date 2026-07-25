# Setup — standing carshorts up on a machine

The whole stack installs with **one script**. It's idempotent (safe to re-run)
and self-verifying, and it **never** touches your secrets or uploads anything —
it prints exactly what only you can do at the end.

> **Why this exists:** carshorts is a *daily* channel, so the system must run on a
> machine that's **always on** — your desktop or a small cloud VM. (When Claude
> works on this project, its tools run in a synced sandbox, not your machine —
> so the sandbox's installs and scheduled tasks don't reach your desktop. This
> script is how you get the real thing running where it can upload daily.)

## Windows

```powershell
cd "D:\Personal Projects\carshorts"
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass   # allow the script this session
.\tools\setup.ps1
```

Installs Python 3.12, ffmpeg, Node LTS, the `claude` CLI (via winget/npm), builds
`.venv`, installs the package, sets `PYTHONUTF8=1` and puts ffmpeg on PATH, and
registers two daily Scheduled Tasks. Flags: `-SkipInstall`, `-SkipTasks`,
`-Time 08:00`.

> If Node was installed on this same run, `npm`/`claude` may not be on PATH yet —
> **open a new terminal and re-run** `.\tools\setup.ps1` to finish the CLI step.

## macOS / Linux

```bash
cd ~/carshorts
./tools/setup.sh
```

Uses Homebrew (macOS) or apt/dnf/pacman (Linux), builds `.venv`, and adds two
daily **cron** jobs. Flags: `--skip-install`, `--skip-cron`, `HEARTBEAT_TIME=08:00`.

## A brand-new laptop, start to finish

1. Install git; `git clone <your repo> carshorts && cd carshorts`.
2. Run the setup script for your OS (above).
3. Drop in the files that are **not** in git (they're gitignored secrets/assets):
   - `.env` — copy `.env.example`, fill `GROQ_API_KEY`, `GEMINI_API_KEY`,
     `PEXELS_API_KEY`. Add `ANTHROPIC_API_KEY` if you want the agents.
   - `client_secret.json` + `youtube_token.json` — Google OAuth for upload +
     analytics (one-time setup documented at the top of `src/carshorts/publish.py`).
   - `assets/` — your curated car pools, `assets/fonts/Montserrat-Black.ttf`, and
     `assets/music/`. Without these the render pool is empty (it will fall back to
     auto-fetching vetted Wikimedia stills).
4. Confirm it's alive:
   ```
   .venv\Scripts\python -m carshorts heartbeat --status      # Windows
   ./.venv/bin/python  -m carshorts heartbeat --status       # macOS/Linux
   ```
5. Optional — enable the agents (verified specs + auto asset pools for new cars):
   authenticate the CLI (`claude`, then `/login`) **or** set `ANTHROPIC_API_KEY`
   in `.env`. The agents run headless, budget-capped at 12 runs/day.

## What runs, and when

- **`carshorts-heartbeat`** (daily, 08:00) — refreshes analytics, decides, drafts
  the next calendar slot, writes an owner report. **It never publishes.** Both
  gates (script approval, final watch) stay yours.
- **`carshorts-retention-watch`** (daily, 09:00) — pulls per-second retention
  curves as YouTube releases them and maps drop-offs onto script beats.

## Daily loop

1. The heartbeat leaves a fresh draft in the queue overnight.
2. You open the review portal — `python -m carshorts portal` → http://localhost:8787
   — watch it, tag beats, and **Approve** (premium final) or **Rework**.
3. After the final's second approval, it publishes. Gates 1 and 2 are always yours.

## Verifying / removing

```powershell
schtasks /query /tn "carshorts-heartbeat"          # Windows: is it registered?
schtasks /delete /tn "carshorts-heartbeat" /f      # remove
```
```bash
crontab -l | grep carshorts                         # Unix
crontab -e                                          # edit/remove
```
