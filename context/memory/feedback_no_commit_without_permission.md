---
name: feedback-no-commit-without-permission
description: "Never git commit or push on the carshorts project without the owner's explicit permission."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 1340d9e1-8c7d-4116-974f-2acb4463ee4f
  modified: 2026-07-22T22:33:12.342Z
---

On carshorts, never run `git commit` or `git push` without the owner's explicit permission (stated 2026-07-23). Make working-tree edits freely, but leave committing to the owner's call.

**Why:** the owner wants to review/control what enters version history themselves.

**How to apply:** edit files as needed; when work is ready, tell the owner what changed and ask before committing. Never commit/push proactively, even when a change looks complete or tests pass. Related: [[project-carshorts-windows]].
