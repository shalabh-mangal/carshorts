# TASTE CONSTITUTION — the owner's standards, distilled
# EVERY agent reads this BEFORE working. This file is the supervisor's
# context made portable: 12+ review rounds, live incidents, and the
# approved house style. When your output conflicts with this file, this
# file wins. Supervisor updates it after every review round.

## Voice & humor (deadpan channel)
- Deadpan works through CLARITY, not obscurity. If the owner would ask
  "what does this mean?", the audience is already gone. Rewrite plain.
- Gold standard peak (approved 5/5): "Creta is the paneer butter masala of
  Indian SUVs. Every family agrees. Nobody remembers which one they had
  last." — specific, cultural, zero fabricated figures.
- One sharp roast per beat max. Never the same joke shape twice in a video.
- Punchlines may play BARE (no text) — reaction pops only when the written
  reaction is instantly self-explanatory ("PEAK OFF-ROADING." yes;
  "Zero memory." died — owner didn't get it).

## Script physics (hard numbers)
- ≤112 words TOTAL for the deadpan edge voice. 133 words = 68s = QA red.
  Runtime hard cap 63.0s including the loop flash.
- Structure: hook / spec / spec / value / peak / cta. News leads the hook.
- CTA law: ask viewers WHICH CAR NEXT (comment bait) + the spoken words
  "like, share, subscribe" (the engine auto-draws the icon strip).

## Facts (non-negotiable)
- Every figure traces to a fetched source or it does not exist. The
  number-guard is law; never fight it, fix the script.
- ₹ lakh/crore only. A "$" in an India video is an automatic fail.
- Price ranges must not be mislabeled (a full-lineup range is not
  "Petrol Creta"). Say what the number actually covers.

## On-screen text (the pop system)
- Text appears ONLY while its words are spoken (word-exact vs TTS marks).
  No anchor in the voice timeline -> the text does not exist. Ever.
- Figures render cyan #7EE5E3, words white, Montserrat Black, ~9% black
  stroke + soft shadow. YELLOW IS BANNED (clip-farm signal).
- Karaoke rail: pops replace each other; never two rail pops at once.
- The price count-up card holds until its beat ends and owns the screen
  while counting (rail clears during the roll).
- No emoji in overlays (font has no glyphs — tofu boxes). Draw graphics
  procedurally (see the LSS icon strip) in the same stroke language.
- Overlays live inside the safe box: x∈[60,930], y∈[200,1420] on 1080x1920.

## Visuals
- Subject car opens AND closes every video. India-market variant.
- B-roll must match the car's CHARACTER: city SUV never gets offroad/mud
  clips. Car-scoped stock lives in assets/cars/<slug>/stock/.
- License-clean only (Wikimedia CC, official press, Pexels) with credits
  recorded. Watermarks = instant delete.

## Owner workflow (respect it)
- Two-stage approval: draft approve -> premium final -> SECOND approval ->
  only then YouTube. Never upload without the second gate.
- The owner's taste OUTRANKS analyst tactics (the "1 or 2?" poll was
  rival-proven and still rejected — owner call stands).
- Never spend paid/scarce resources without prior approval. Free tools for
  drafts; premium only for approved finals.

## Incident ledger (never repeat these)
1. Removal flags need EXPLICIT removal words from the owner — an LLM once
   invented --no-kwcaps from "text going out of screen" and shipped a
   textless render. LLM proposes, code disposes.
2. edge-tts can pack multiple words into one mark ("Level 2") — matching is
   word-granular now; remember when writing anchors.
3. Possessives break anchors: "Smart money" never matched "money's" —
   anchor on the EXACT spoken tokens.
4. Filenames lie: date-prefixed press photos defeated prefix matching —
   subject checks use name containment + curated aliases.
5. A 156-word script cost three renders. Check the word budget BEFORE
   rendering, not after.

## Agent conduct
- ONE concern per run. Oversized tasks die at the turn cap.
- VERIFY BY LOOKING: extract frames of what you changed (ffmpeg -ss ... )
  and Read the PNGs yourself before reporting done. "Renders without
  error" is not "looks right."
- Report honestly: what you did, what you skipped, what looked wrong.
  A flagged doubt is worth more than a confident miss.
- Unsure about owner intent? Write the question to data/brain_inbox.jsonl
  instead of guessing.
