---
name: ground-facts
description: Build a sourced, confidence-scored spec sheet from trusted sources; flag unverified as CLAIMED.
triggers: specs, facts, research, spec sheet, grounding, claimed, confidence, sources, accuracy
---
Goal: a spec sheet where every fact is either corroborated by trusted sources (high
confidence) or honestly flagged `[CLAIMED]` — never an invented "fact" (the "1.5L
Fronx" class of error). Accuracy is the channel's whole edge.

1. Generation-scoped crawl for a first pass (structured, per-generation):
   `carshorts crawl "<Name>"`

2. RAG grounding over ranked trusted sources (CarDekho / official maker site /
   Autocar / CarWale rank highest; Wikipedia is weak; corroboration → confidence):
   `carshorts research "<Name>" --no-price`
   This writes specs/<slug>.json with a real per-spec confidence. Specs below 0.7
   are marked `[CLAIMED]` by render_spec_sheet and the writer MUST attribute them
   ("the maker claims", "reportedly", "expected") — never as fact.

3. PRICES are never auto-scraped. A price is a one-off, owner-confirmed
   CarDekho/CarWale lookup added to specs_extras/, or "expected ₹X–Y, flagged".
   `--no-price` above enforces this; do not remove it.

4. VERIFY the survivors against CarDekho / the official site by eye. If a spec
   can't be sourced, it does NOT go in — surface the gap, don't invent.

5. Pre-launch / unreleased car with no official page: set every spec confidence
   < 0.7 so the whole sheet renders `[CLAIMED]`, and prefer the `upcoming` format.

Gate: no unsourced number reaches a script as fact. When in doubt, flag it CLAIMED.
