---
name: source-footage
description: Get a car's footage pool render-ready — coverage, provenance, safe ingest, visual vet.
triggers: footage, clips, coverage, ingest, b-roll, broll, provenance, license, licensing, plate, watermark
---
Goal: enough CLEAN, DISTINCT, PROVENANCE-CLEARED clips that a render never repeats
footage and never ships a plate/watermark. Never invent footage; surface gaps.

1. ASSESS what exists:
   `carshorts footage <slug>`
   Read the report: clean distinct video vs target cuts (one clip per cut — the
   no-repeat rule), the per-angle histogram, missing essential angles
   (front/side/rear/interior/action), and any clip flagged UNVERIFIED source.

2. If clips have UNVERIFIED source — STOP and resolve licensing first. Never let a
   clip of unknown origin stay in own/. Ripped/watermarked ad footage (readable
   plates, burned-in "creative representation only" disclaimers) is refused —
   offer legal routes (owner shoot, official press kit, licensed stock). This is
   the owner's hard rule.

3. To add owner/press-kit footage: drop files in assets/inbox/, then
   `carshorts ingest --car "<Name>" --source "<where from>" --license "<owned|press-kit|licensed|CC-BY>"`
   Ingest classifies each clip, cuts clean ones into segments under
   assets/cars/<slug>/own/, sends plated/watermarked ones to review/, and records
   provenance to footage_sources.json.

4. To top up GENERIC motion (never the subject car — identity comes from stills):
   the renderer auto-fetches vetted stock (Pexels/Pixabay) only when no own clips
   exist. If you fetch stock/CC manually, VET IT BY LOOKING before it enters the pool:
   `carshorts assetvet assets/cars/<slug>/images --subject "<Name>" --apply`
   (blurs recoverable plates, quarantines watermarks/wrong-vehicle).

5. RE-ASSESS: `carshorts footage <slug>` again. Do not proceed to a render until it
   reads READY (shortfall 0, no missing essential angle) — or, for an unreleased
   car with no real footage, pin owner/concept clips via a shot plan (concept
   b-roll NEVER passed off as the actual car).

Gate: a render blocked on a footage RED is a footage gap you cannot invent past —
surface the shopping list to the owner, don't ship repeated/looped clips.
