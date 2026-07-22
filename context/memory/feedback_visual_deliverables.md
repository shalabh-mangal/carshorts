---
name: feedback_visual_deliverables
description: "For plans/roadmaps/presentations, deliver concise visuals (PDF, flowchart, diagram), not long markdown essays."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 62beffc4-edec-448e-98d2-11a6db3217d9
---

For plans, roadmaps, and presentations the user wants **concise, visual deliverables** — a rendered PDF, a flowchart, a diagram — NOT long markdown essays or walls of text. They repeatedly rejected verbose plan files ("who will read such big file?") and a mermaid flowchart they found ugly, then asked for a proper PDF.

**Why:** they're presenting/deciding, not reading prose; visuals communicate journeys and comparisons faster.

**How to apply:**
- Default to a rendered artifact: PDF (reportlab is installed; no Chrome/weasyprint/wkhtmltopdf — render programmatically and self-verify by rasterizing with `qlmanage -t` + Read the PNG), or an HTML Artifact, or `show_widget`.
- Compare scenarios side-by-side (e.g. confident vs hesitant user journeys), step-by-step one-liners, with timelines.
- Tag FE-heavy vs BE-heavy work explicitly.
- reportlab base fonts have NO emoji glyphs → emoji render as tofu boxes; use colored shape markers instead.
- Keep it tight; prefer tables/diagrams over paragraphs. Still lead reasoning in plain English (see [[feedback_brainstorm_style]]).
