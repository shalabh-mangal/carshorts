---
name: feedback-brainstorm-style
description: "For architecture/design brainstorming, user wants plain-English reasoning about what is happening, what isn't, and what to think about — not file paths, code blocks, or implementation plans."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 7109386a-b614-43ed-a4fa-e3f4c96981b4
---

In brainstorming / architecture-rethink discussions, lead with prose reasoning, not implementation artefacts. Explain:
- What is happening today in plain words (the current model, the assumptions baked into it)
- What is NOT happening (the gaps, blind spots, things the system doesn't even know about itself)
- What the customer/business experiences as a consequence
- What we should be thinking about as a principle / mental model — before deciding on files, tables, endpoints

**Why:** User explicitly asked twice for brainstorming and twice got jumped to a code-level plan with file paths and table DDLs. They want the architect's vision rendered as English first so they can pressure-test the thinking, not the wiring. Code-level detail can come later, once the framing is agreed.

**How to apply:** When the user says "brainstorming", "think like an architect", "out of the box", "in plain English", or shows the same intent in different words — keep the response narrative. No file:line references, no DDL, no enum lists, no phase tables unless they ask. End with sharp questions or trade-offs, not an ExitPlanMode.
