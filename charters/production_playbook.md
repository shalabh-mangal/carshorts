# Production Playbook — how a video gets made (the working method)

This charter encodes the way the owner + Claude have been producing videos by
hand, so the automated pipeline and the headless agent (`agents/agent.py`) work
the SAME way. Read alongside `TASTE.md` (the LAW) and the proven `learnings`.

## 1. Facts first — accuracy is the channel's whole edge
- Specs come from a SOURCED sheet, verified against **CarDekho / the maker's
  official site** — not Wikipedia guesses. Prices are a one-off CarDekho/CarWale
  lookup (owner-confirmed); NEVER auto-scrape prices.
- **Pre-launch / unreleased car** (no official spec page): set every spec's
  `confidence < 0.7`. `render_spec_sheet` then marks them `[CLAIMED]` and the
  writer MUST attribute them ("the maker claims", "reportedly", "expected") —
  never as fact. Prefer the `upcoming` format. Price → "expected ₹X–Y, flagged".
- If a fact can't be sourced, it doesn't go in. Surface the gap; don't invent.

## 2. Script — apply what the data proved (see learnings)
- **Hook**: question + a hero NUMBER in the first 2s (Sonet's winning shape).
- **Spec beat = the #1 drop-off**: it MUST bridge and ESCALATE the hook ("here's
  the trick…") and land as a payoff — one tight line, never a flat number recital.
- **Tight**: ~70–90 words (Sonet 71 won; 165 died). Loop-friendly close.
- **Like at the dopamine peak**; **rivalry-poll CTA** ("A or B? comment 1 or 2");
  CTA ≤ 4s with like/share/subscribe.
- Every named number/feature gets a synced on-screen overlay (anchors normalize
  like the TTS, so hyphenated/unit labels don't drop).

## 3. Voice
- Channel voice = the owner's cloned **calm/deadpan (chatterbox)** for finals &
  drafts. ElevenLabs only for finals, and only after the owner approves the spend.

## 4. Footage — real first, honest always
- Owner's real/press footage leads. New stock/CC gets a **visual vet-grid**
  (LOOK at it — tags lie; blur/exclude plates, no watermarks/ripped content)
  BEFORE it enters the pool. No repeated/looped clips (clip ≥ its on-screen span).
- **Unreleased car**: no real footage exists → use honest CONCEPT b-roll
  (charging, roads, dashboards) that is NEVER passed off as the actual car.

## 5. Blockers & gates
- Don't ship garbage — call out missing facts/footage honestly.
- Every render must end **QA-green** before the owner sees it.
- **Gate 1** (script) and **Gate 2** (final watch) belong to the owner. Always.
- Uploads go to **carsInShorts** only — the channel guard aborts otherwise.

## 6. After publish — close the loop
- Feed each video's analytics (retention curve → per-beat drop) back into
  **learnings + critic + script studio** (all three), not one video.
