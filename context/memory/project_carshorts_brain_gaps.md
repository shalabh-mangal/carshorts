---
name: project-carshorts-brain-gaps
description: "carshorts brain gap analysis + agreed 6-step build order (three missing organs: eyes, lab, heartbeat)."
metadata: 
  node_type: memory
  type: project
  originSessionId: faea6523-542d-47bc-ac54-9dd402f1cb21
  modified: 2026-07-23T08:19:31.026Z
---

Owner directive 2026-07-23: build carshorts into a system with its own brain. Diagnosis after a full-codebase audit + the first real analytics pull — the factory (hands) is strong; the brain lacks three organs. Full detail lives in `ROADMAP.md` under "BRAIN GAP ANALYSIS". See [[project-carshorts-windows]].

**The core limitation:** the system learns only from its own output, from 5 videos, of which YouTube had processed **4% of views (33 of 767)**. Every retention % quoted before 2026-07-23 was computed on ≤26 views and is noise — do not act on it.

**Measured baseline (channel carsInShorts, `UCtT7HC6Jcetn2d5QBx8UktA`, 2026-07-23):** 5 uploads, 767 views, 1 subscriber (channel created 2012 but dormant → cold start). Engagement is the loudest *trustworthy* signal and it's weak: **~0.65% like rate, ~0.13% comment rate**. Traffic is dominated by the SHORTS feed, so distribution is working — this is not a technical failure. `impressions`/`impressionsClickThroughRate` return HTTP 400 on the Analytics API → **CTR is YouTube-Studio-only, a permanent automation blind spot**.

**Three missing organs:**
1. **Eyes (perception)** — no competitor intel *module* (agents/analyst.md is only a charter that ran once); no news/press crawler (crawl.py is Wikipedia+specs only, so prices/news come from hand-curated `specs_extras/` — the human bottleneck blocking "daily"); topic choice is a hardcoded CARS list.
2. **Lab (causal inference)** — no experiment ledger, nothing enforces one-variable-at-a-time, and **no significance gate before a lesson edits the writer prompt**. `learnings.json` is a flat LLM-appended list with no confidence/evidence/expiry → the system can teach itself superstitions.
3. **Heartbeat (autonomy)** — nothing runs the day; cadence stopped after 2026-07-22. Cadence is the *data-generation engine*, not a growth tactic. (Retention auto-recheck shipped 2026-07-23.)

**Agreed build order:** 1) daily orchestrator → 2) competitor/trend intel → 3) news+press crawler → 4) experiment ledger + significance gate → 5) engagement + first-frame engineering → 6) ffmpeg-native fast renderer.

**Framing to keep:** nobody reverse-engineers the YouTube algorithm; you beat it by out-iterating it — publish consistently, measure honestly, change one variable at a time. Never let a thin sample write a lesson.
