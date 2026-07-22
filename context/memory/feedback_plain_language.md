---
name: feedback-plain-language
description: "Explain in short, plain, simple language with context — avoid jargon, class-name/file:line dumps, and long dense tables in explanations."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: e59095b9-3ce0-47dd-92b8-9aaa42fe68ce
---

When explaining findings, designs, or opinions, use **short, plain, simple, everyday language** and give the context. Avoid jargon, code-symbol soup (class names, `file:line` lists), and long dense tables unless the user asks for that depth.

**Why:** the user said "I didn't understand your language" after a jargon-heavy audit write-up full of class names and technical tables. They want easy-to-understand explanations.

**How to apply:** lead with a plain-English summary a non-engineer could follow. Explain what something IS and why it matters before any technical detail. Keep technical specifics (file:line, exact method names) available but secondary / on request. Short over exhaustive. Pairs with [[feedback_brainstorm_style]] (plain-English reasoning first) and [[feedback_visual_deliverables]] (concise visuals over essays).
