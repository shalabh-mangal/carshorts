---
name: ground-facts
description: Build a sourced, confidence-scored spec sheet from trusted sources; flag unverified as CLAIMED.
triggers: specs, facts, research, spec sheet, grounding, claimed, confidence, sources, accuracy
---
Goal: a spec sheet where every fact is either corroborated by trusted sources (high
confidence) or honestly flagged `[CLAIMED]` — never an invented "fact" (the "1.5L
Fronx" class of error). Accuracy is the channel's whole edge.

1. RAG grounding over ranked TRUSTED sources ONLY — tier-1 India spec authorities
   (CarDekho / CarWale / Autocar / ZigWheels) + official maker sites (Nexa etc.).
   Wikipedia is REMOVED as a fact source (it shipped wrong India specs — the "1.5L
   Fronx" class), so it can never enter a sheet:
   `carshorts research "<Name>" --no-price`   (`crawl` is now an alias for this)
   This writes specs/<slug>.json with real per-spec confidence. Specs below 0.7
   are marked `[CLAIMED]` by render_spec_sheet and the writer MUST attribute them
   ("the maker claims", "reportedly", "expected") — never as fact.

2. If no trusted source is reachable (many are JS-rendered or bot-block plain
   fetches), the sheet comes back thin/empty — that's honest, not a failure. Fill
   it from the OFFICIAL maker site / CarDekho by hand (paste the page); write each
   fact with its source_url. Never inject an unsourced number, even flagged.

3. PRICES are never auto-scraped. A price is a one-off, owner-confirmed
   CarDekho/CarWale lookup added to specs_extras/, or "expected ₹X–Y, flagged".
   `--no-price` above enforces this; do not remove it.

4. VERIFY the survivors against CarDekho / the official site by eye. If a spec
   can't be sourced, it does NOT go in — surface the gap, don't invent.

5. Pre-launch / unreleased car with no official page: set every spec confidence
   < 0.7 so the whole sheet renders `[CLAIMED]`, and prefer the `upcoming` format.

Gate: no unsourced number reaches a script as fact. When in doubt, flag it CLAIMED.
