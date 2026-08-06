# Autonomy Roadmap — make the system self-improving, at human quality

Goal: the system produces publish-quality Shorts **by itself**, learning from every
video. The owner keeps only the taste gates (Gate 1 script, Gate 2 final).

## Why it isn't autonomous yet (diagnosed from real interventions)
The LLM is **not** the bottleneck — scripts are good. Every manual save-the-day fell
into one of these:

1. **Blindness** — it can't SEE its own output. A hook clip was two plated Mercedes
   G-Wagons passed off as the MG; deterministic QA (loops/repeats/duration) can't
   judge "wrong car / readable plate / clip doesn't match narration."
2. **Weak fact grounding** — the researcher used Wikipedia and produced a wrong
   "1.5L Fronx"; no trusted-source retrieval or confidence-scored facts.
3. **Open correction loop** — the brain critic *flags* ("spec cliff", "CTA overruns")
   but a human reads it and edits; it doesn't auto-revise + re-render.
4. **Judgment under ambiguity** — claim-framing a pre-launch car, "concept b-roll
   never labeled as the car", pinning real footage to the hero beat.
5. **No real footage of the subject** — no model invents footage of an unreleased car.

## Priorities (highest leverage first)
| # | Introduce | Fixes | Status |
|---|---|---|---|
| 1 | **Vision QA as a hard gate** (multimodal, every render) | Blindness — plates, wrong/rival vehicle, clip↔narration, dull frame 1 | **✅ SHIPPED** — `produce` runs VQA, `qa.py` gates on "no blocking vision defects" |
| 2 | **RAG over trusted sources** (CarDekho/official/Autocar/CarWale) + confidence | Fact grounding; auto `[CLAIMED]`; kills the "1.5L Fronx" class | **✅ SHIPPED** — `webresearch.ground_specs` + `merge_and_score` (ranked sources, corroboration → real confidence) |
| 3 | **Close the agent loops** (render→assess→auto-fix→re-render until ship/owner) | Removes "human at every seam" | **✅ SHIPPED** — `agents/autoloop.py` (`carshorts autoloop <slug>`): quarantines vision-blocked clips + revises weak scripts, re-renders, surfaces footage gaps |
| 4 | **Real footage pipeline** (owner press-kit ingest, licensed-clip APIs) | The true ceiling on quality (non-AI) | **✅ SHIPPED** — `sourcing/footageplan.py` (`carshorts footage <slug>`): coverage (distinct clips vs cuts + per-angle histogram + missing essentials) & provenance (unverified-source flag) → a shopping list, wired into the autoloop's `surface`; `ingest` now records `footage_sources.json`; second licensed video API (Pixabay) + `build_video_source()` chooser |
| 5 | **Skills** — each workflow codified/invokable | Consistency (playbook charter = skill #1) | started |
| 6 | **SLM (local)** for cheap high-volume classify/tag | Cost + offline resilience (optimization, not quality) | later |
| 7 | **Fine-tune** a small model on our winning scripts + retention | Channel-voice consistency | later (needs more winners) |

## Self-improving loop (the north star)
Every published video → analytics (per-beat retention) → **learnings + critic + script
studio** (all three) → next video is written *and screened* against what worked. Each
manual catch becomes a permanent guard + a learning (already done for: channel, repeat,
stock-leak, overlay-anchor, claim-framing). Vision QA + RAG close the last big gaps.

**If we do one thing first:** the vision QA gate — it converts the mistakes a human
catches by eye (plates, wrong car, mismatched clip) into automatic blocks.
