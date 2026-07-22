---
name: feedback-meaningful-naming
description: "Use meaningful, self-explanatory nomenclature for variables/params/methods — no terse or generic names."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 2a8881fe-a3c5-4aa4-8fc3-15ec94bf7347
---

Always name variables, parameters, methods, and fields meaningfully and self-explanatorily. Avoid terse/generic names (`e`, `lower`/`upper`, single letters) — prefer intent-revealing names (`eventToBeInserted`, `windowStart`/`windowEnd`).

**Why:** the user has repeated this multiple times, and a PR reviewer (@sunil-sangwan-ltcv) flagged terse names ("better variable names") on thrust #213. Meaningful naming is a standing expectation, not a one-off.

**How to apply:** when writing or editing code, pick descriptive names by default; if I introduce a generic/terse name, rename before finishing. Applies to new code AND when touching existing terse names in files I edit. Pairs with [[feedback_ask_before_implementing]] and [[feedback_verify_before_answer]].
