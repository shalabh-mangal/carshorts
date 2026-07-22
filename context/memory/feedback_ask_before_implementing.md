---
name: feedback-ask-before-implementing
description: "For implementation tasks, present multiple approaches and get a pick BEFORE coding — don't jump straight to editing."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: fdc761ea-7d90-4be0-af79-1f502574a8df
---

For code/feature tasks, do NOT jump straight to implementing. First lay out the plan and **multiple alternative approaches** (trade-offs each), and let the user choose before any edits.

**Why:** user wants to weigh options and control the approach; several times I implemented a reasonable-but-unconfirmed choice (e.g. disposition filter = VKYC-only option set) that may not be what they'd have picked.

**How to apply:** for anything beyond a trivial one-liner, respond with 2–4 concrete approaches + a recommendation, then wait for their pick. Scoping/exploration (read-only) is fine to do first; the *gate* is before writing code. Pairs with [[feedback_brainstorm_style]] (plain-English reasoning first) and [[feedback_verify_before_answer]].
