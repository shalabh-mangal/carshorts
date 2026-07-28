---
name: feedback_portal_top_notch
description: "The review portal is the owner's primary review surface — keep it running and top-notch."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: faea6523-542d-47bc-ac54-9dd402f1cb21
  modified: 2026-07-27T04:23:58.419Z
---

The owner reviews every draft through the review portal ([[project_carshorts_windows]]) at
http://localhost:8787, and wants it kept in top-notch quality — treat it as a first-class
product, not a debug tool.

**Why:** Gate 1 (script/draft) and Gate 2 (final) both happen in the portal; if it's down or
janky, the owner is blocked from approving anything.

**How to apply:**
- It's a LOCAL server (`carshorts portal`, no hosting) — "down" just means the process isn't
  running. Launch with `tools/portal.cmd` (Windows) / `tools/portal.sh`; it opens the browser
  and stays up. For always-on, it must run on the persistent host ([[project_carshorts_sandbox_env]]).
- When touching FE code, verify end-to-end after: video loads (readyState 4), both Review +
  Analytics tabs render, no console errors. A stray JS error can kill the whole page (see the
  past `recipe\'s` apostrophe bug).
- Analytics avg-view% can legitimately exceed 100% for Shorts (loops re-watch) — not a bug.
