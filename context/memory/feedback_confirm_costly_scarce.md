---
name: feedback-confirm-costly-scarce
description: Ask before spending any scarce/expensive/limited resource — never act on your own.
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 26349845-c703-4b79-980e-2066eb5abd0c
---

Before consuming anything **rare, costly, or limited** — paid API credits (e.g. ElevenLabs), quota-capped free tiers, anything metered or with real money/usage cost — STOP and ask the user first. Never spend or trigger it on your own initiative, and never batch such operations (batching multiplies the cost).

**Why:** batched 3 ElevenLabs voiceovers "to compare" when only 1 was needed, burning ~2,762 of 10,000 monthly credits. The comparison should have stayed on the free voice.

**How to apply:** when an action touches a costly/scarce resource, present the expected cost (credits/chars/quota) and the cheaper alternative, then wait for an explicit go-ahead before running. Prefer the free path for iteration; reserve the expensive path for the final, confirmed step. One item at a time, never a batch, unless the user says so. Extends [[feedback-ask-before-implementing]] — that's about design approaches; this is about cost/resource gating.
