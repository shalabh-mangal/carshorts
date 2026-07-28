---
name: project-carshorts-windows
description: "carshorts now runs on a Windows box — env standup, the UTF-8 bug, credential/asset state, how to run."
metadata: 
  node_type: memory
  type: project
  originSessionId: 1340d9e1-8c7d-4116-974f-2acb4463ee4f
  modified: 2026-07-22T22:08:12.180Z
---

carshorts has a working clone at `D:\Personal Projects\carshorts` on **Windows 11** (separate from the Mac origin `~/Github/thrust`). Stood up 2026-07-23; all 37 pytest tests pass.

**Environment (this machine):**
- Python 3.12 (`C:\Users\Admin\AppData\Local\Programs\Python\Python312`), project venv at `.venv` (installed via winget). Deps: `pip install -e ".[dev,video,crawl,publish,real]"`.
- ffmpeg 8.1.2 at `C:\Users\Admin\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_*\ffmpeg-8.1.2-full_build\bin` — **NOT on the PATH the tool shells inherit**; prepend that bin to `$env:PATH` for any render (produce/qa/audiopolish call bare `ffmpeg`/`ffprobe`).

**PYTHONUTF8=1 is REQUIRED on Windows** (set persistently via `setx` on 2026-07-23). Default `Path.read_text()`/`write_text()` use cp1252 here, which mojibakes `₹ — · …` — caught by the Thar value card rendering "Â‚¹12.99 LAKH". The durable in-repo fix (add `encoding="utf-8"` to every read_text/write_text/open — must do reads AND writes together or writes crash on `₹`) is still PENDING; the env var is the current fix. See [[project-carshorts]].

**Credentials present** (owner added 2026-07-23, all gitignored): `.env` (GROQ/GEMINI/PEXELS/ELEVENLABS + voice id), `client_secret.json`, `youtube_token.json` (valid refresh token, `yt-analytics.readonly` scope). **Analytics verified working** — `python -m carshorts.analytics --video <id>`. Live: Thar `EXCHHyUDyyg` (73 views), Creta `NXa-7sG13Uw` (10), older Thar `mPbjAt4kSoE` (136). Per-video avg-view% returns 0 (YouTube lag/low-view threshold); channel-level shows 32-58%.

**Assets NOT transferred** (gitignored): only `Montserrat-Black.ttf` + a few fetched Thar stills exist; Creta pool empty; no `assets/{music,stock,inbox}`. Renders auto-fetch Wikimedia CC stills, but **that path has NO plate/watermark/generation guard** (unlike `ingest.py`) — the fetched Thar stills had readable plates and one wrong-gen watermarked image. Never publish auto-fetched stills without vetting/blurring. Candidate improvement: add a plate/watermark vet to `WikimediaImageSource.fetch`.

**Render a free draft:** prepend ffmpeg bin to PATH, then `python -m carshorts.produce --script-file scripts/<slug>_<persona>.script.json --spec specs/<slug>.json --skip-factcheck --persona deadpan --out out/<name>.mp4`. Portal: `python -m carshorts.portal` → http://localhost:8787.

**Open issue:** the locked `thar_deadpan.script.json` runs 69.7s (>63s cap) at NeerjaExpressive +3% (~121 words vs TASTE ≤112) — needs trimming before it would pass QA green.
