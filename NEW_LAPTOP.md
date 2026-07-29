# carshorts — New‑Laptop Onboarding + Roadmap

**Read this first on the new machine (ASUS TUF F16 · i7‑14650HX · RTX 5060 8GB · 16GB RAM).**
It gets you running in ~20 min, then hands over full context and the plan.
Companion docs: `README.md` (how it works), `SETUP.md` (install detail),
`ROADMAP.md` (tier ladder), `CLAUDE.md` (agent house‑rules), `context/README.md`
(knowledge map). Git branch with all recent work: **`feat/brain-organs`**.

---

## 0. What this is (30 seconds)
A self‑correcting **YouTube Shorts factory for Indian cars**. Spec sheet → script
(free LLM) → phrase‑synced render (ffmpeg) → your Gate‑1 review → premium final →
your Gate‑2 → upload. **Runs 100% free** (GROQ/Gemini free LLMs, edge or your
**cloned** voice, Wikimedia/Openverse stills, Gemini‑free vetting). Two human
gates are yours and never bypassed.

---

## 1. Get running on the new laptop (do these in order)

**a) Get the code.** Either push `feat/brain-organs` to your git remote and clone
it, **or** copy the whole `carshorts` folder (incl. `.git`) from the old machine.

**b) Copy the SECRETS that git does NOT carry** (they're gitignored — bring them
from the old machine's folder, do not commit them):
- `.env` — GROQ/GEMINI/PEXELS keys (+ optional ELEVENLABS). **All free tiers.**
- `client_secret.json`, `youtube_token.json` — YouTube OAuth (uploads/analytics).
- (`data/voice/owner_reference.mp3` — your voice clone reference — **is** committed, so it comes with the repo.)

**c) Run setup** (installs Python 3.12, ffmpeg, Node, venv + all extras incl. the
voice engine, CUDA torch for the RTX 5060, scheduled tasks, smoke test):
```powershell
.\tools\setup.ps1
```
Re‑run it in a NEW shell if it says npm/PATH isn't ready yet (idempotent).

**d) Turn on YOUR cloned voice** — add one line to `.env`:
```
CARSHORTS_VOICE_ENGINE=chatterbox
```
(First render downloads the voice + whisper models, ~few GB, once.)

**e) Verify:**
```powershell
.\.venv\Scripts\python.exe -m carshorts heartbeat --status
.\tools\portal.cmd          # opens the review station at http://localhost:8787
```

---

## 2. This laptop — what it can do
- **Voice (Chatterbox clone):** RTX 5060 8GB is plenty → **fast**. CPU also works, slower.
- **Motion leap (LTX‑Video i2v):** 8GB is the **entry tier** — good for short vertical Shorts clips at 512–720px; won't run the 40GB flagships (Wan 2.2).
- **RAM:** 16GB is a touch tight for image‑to‑video; a **32GB DIY upgrade** (2 SO‑DIMM slots) is the one worthwhile add later. Not needed for voice.
- The old cloud sandbox had **no GPU** and was ephemeral — this laptop is now the real host for the daily runs + the leaps.

---

## 3. What's DONE (state as of handoff)
- **World‑class code:** domain subpackages under `src/carshorts/`, unified `carshorts <command>` CLI, central `core/paths.py` (runs from any dir), **162 tests green, ruff clean.**
- **Zero‑spend pipeline:** free scripts (GROQ), free stills (Wikimedia broadened + throttled + Openverse bonus), free vetting (Gemini), edge voice. Proven end‑to‑end.
- **Voice leap SHIPPED (this session):** `ChatterboxTTSProvider` in `adapters/tts.py` — clones your voice, speaks **English / Hindi / Hinglish** (multilingual model), phrase‑sync via faster‑whisper (proportional fallback), Perth‑safe, GPU‑auto, graceful fallback to edge. Switch on with `CARSHORTS_VOICE_ENGINE=chatterbox`.
- **Quality guards:** per‑image `assetvet` (plates/wrong‑vehicle/watermarks) is the hard guard; post‑render VQA is **advisory** (vision is noisy — don't hard‑gate on it); wrong‑vehicle generic stock quarantined.
- **Brezza produced free:** draft + premium final (edge voice) rendered, you approved Gate 1 (rating 4); it sits at **`final_review` (Gate 2)** — one step from publish. Data in `data/queue/maruti-suzuki-brezza.json`.
- **Portal:** works (Review + Analytics tabs, video plays, no errors). Launch with `tools/portal.cmd`.

**Git:** everything is on **`feat/brain-organs`**, `main` untouched, **nothing pushed** (your call). Consider pushing/merging once you're set up.

---

## 4. IMMEDIATE next steps on the new laptop
1. Finish setup (§1), set `CARSHORTS_VOICE_ENGINE=chatterbox`, restore Perth watermark install (responsible‑AI marking) — see §6.
2. **Re‑render Brezza with your cloned voice** and re‑review:
   ```powershell
   .\.venv\Scripts\python.exe -m carshorts pipeline "Maruti Suzuki Brezza" --persona hype --format five_things --no-agent
   ```
   (Or publish the current final: `... pipeline --publish maruti-suzuki-brezza` — uploads to YouTube, **your** action.)
3. Pick the next car (no repeats without fresh news — see the rule below) and ship one.

---

## 5. Roadmap — the leaps, in order
1. **Voice (DONE):** cloned, multilingual, free. → *Verify quality on the GPU; restore Perth watermark.*
2. **Hinglish move** — the voice is ready; the rest is a content‑layer project, all free:
   - Scripts in Hinglish/Hindi (free LLM can do it — prompt work in `writing/prompts.py`).
   - **Devanagari captions** — add a Hindi font (e.g., Noto Sans Devanagari) to the renderer.
   - Number/fact‑guard tuned for Hindi text.
   - Flip per‑video with `--language hinglish` (already threaded to the voice).
3. **Motion leap — "Living Stills"** (the big visual jump): **image‑to‑video** on our real stills via **LTX‑Video** (runs on the 5060). i2v‑only (animate real photos → stays factual). Add a frame‑integrity QA gate.
4. **Agents on a free model** — the scriptwright/curator as a small tool‑loop on GROQ‑Llama/local Ollama (the `LLMClient` already supports both). No paid `claude setup-token` needed. See ROADMAP.
5. **REACH — the real business constraint** — videos get ~26–471 views; experiments need ~500. Craft is ahead of distribution. Levers: titles/thumbnails/hooks, hashtags, cadence. This is where growth actually comes from.

Optional premium (paid, out of current scope): ElevenLabs voice, Wan 2.2 motion (40GB rented GPU).

---

## 6. Known debts / gotchas (don't get bitten)
- **Perth watermark:** on the sandbox it stubbed to a no‑op (the code handles this gracefully). On the new laptop, ensure `resemble-perth` installs fully so AI‑voice outputs are watermarked (good practice for a cloned voice). Retry the `[voice]` install if needed.
- **Windows UTF‑8:** `PYTHONUTF8=1` must be set (setup does it) or ₹ and Devanagari mojibake. Wrappers set it too.
- **Wikimedia rate‑limit:** image fetch is throttled + uses a compliant User‑Agent. Optionally set `CARSHORTS_CONTACT=you@email` in `.env` for higher limits. Pools **cache permanently** per car, so the 429 pain is one‑time.
- **Vision QA is advisory, not a gate** — it false‑positives on already‑blurred plates and flags different frames each run. Trust `assetvet` (pre‑render) + your eye.
- **No‑repeat rule:** don't re‑make a car we've published (Creta, Thar, Nexon, Swift, Brezza) unless there's a real facelift/news event.
- **Never commit/push without the owner's OK.** Never auto‑publish — Gate 2 + publish are yours.
- **Model downloads** (voice ~few GB, whisper) happen on first use — expect a slow first render, fast after.

---

## 7. Where things live
```
src/carshorts/        core/ adapters/ writing/ rendering/ quality/ sourcing/
                      intel/ agents/ orchestration/ publishing/ portal/  + cli.py
charters/             role charters + TASTE.md (owner taste law)
data/scripts/         locked .script.json per video
data/voice/           owner_reference.mp3 (voice clone reference)
data/queue/           approval cards (Gate 1/2 state)
assets/cars/<slug>/   per-car stills/press/stock (committed, plate-vetted)
specs/ specs_extras/  fact sheets (specs crawled + CarDekho-verified; prices manual)
out/                  renders (gitignored)
tools/                setup.ps1/.sh, portal.cmd, heartbeat/retention wrappers
```
Commands: `carshorts <heartbeat|pipeline|produce|portal|crawl|newscrawl|analytics|…>`.

---

## 8. One‑paragraph "why", so choices make sense
The owner does **taste + two gates**; the machine does everything else, **for free**,
and **learns** (retention → weakest beat → next script). Accuracy is sacred
(facts only from sourced sheets; never invent an image; prices are manual). The
binding constraint is **reach**, not craft — keep that in view when prioritising.
