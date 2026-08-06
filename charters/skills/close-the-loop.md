---
name: close-the-loop
description: Turn a published video's analytics into permanent, three-layer improvements.
triggers: analytics, retention, learnings, improve, metrics, performance, drop-off, self-improve, feedback
---
Goal: every published video makes the NEXT one better — a fix goes into all three
layers so it applies to every future video, not just a one-off edit.

1. Fetch and read the numbers (treat <500 views as weak signals):
   `carshorts analytics`   then   `carshorts retention-watch <slug>`
   Identify the per-beat drop-off (hook swipe, the spec cliff, the CTA tail).

2. Diagnose the CAUSE from evidence, not vibes — re-watch the beat where retention
   falls. Tie the drop to a concrete, fixable rule (e.g. "static frame 1", "spec
   beat recites instead of escalating", "CTA > 4s").

3. Apply the fix in ALL THREE layers (this is the non-negotiable part):
   - knowledge/learnings.json  — append a dated [high][data][<slug>-<date>] line.
   - agents/critic.py          — so the pre-Gate critic catches it on every render.
   - writing/scriptbrain.py    — so the Script Studio writes to avoid it up front.
   A fix in only one layer will regress; a fix in all three is permanent.

4. If the fix taught a durable ACTION the free rule-based brain should take, append
   a line to data/brain_inbox.jsonl for the supervisor to fold into the menu.

5. Verify: `pytest -q` stays green, and a fresh render's critique reflects the new
   check. Never ship a "learning" that isn't enforced somewhere.

Gate: a learning that lives only in one video's edit is lost. Bake it into the
system (all three layers) or it didn't happen.
