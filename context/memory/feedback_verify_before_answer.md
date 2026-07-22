---
name: feedback_verify_before_answer
description: Always verify claims from source before answering; never assert from assumption/memory. Be token-cautious.
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 1ffa58b5-d9f0-4ef3-abe2-5c6dc6b093d7
---

Before answering factual/technical questions, verify from the authoritative source (code, DB, prod config, live system) — do NOT assert from assumption, prior context, or a single observation. The user was burned by repeated corrections (e.g. claimed POA was the 3rd KYC step from a dev-app observation; prod `workflow_configuration` V1 config actually has POA as step 1 — `POA → Aadhaar → PAN → VKYC`, POA `depends_on: []`).

**Why:** confident-but-wrong answers cost the user trust and rework, especially on stakeholder-facing material.

**How to apply:** for any claim that can be checked, check it (grep the code, query the DB/Metabase, read the config) before stating it. When two sources disagree (e.g. dev app vs prod config), reconcile explicitly and trust the authoritative one for the question asked. Simultaneously **use tokens cautiously** — targeted reads/queries, not broad sweeps; verify the specific fact, don't over-explore.
