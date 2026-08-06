---
name: produce-video
description: Render a locked script to a QA-green, vision-clean draft via the auto-fix loop.
triggers: render, produce, draft, video, autoloop, re-render, rerender, qa, vision
---
Goal: a draft that is QA-green (12 checks) AND vision-clean AND critic ≥ bar, with
NO repeated footage — before the owner ever sees it. Prefer the closed loop; it
auto-fixes what it can and surfaces what it can't.

1. Confirm inputs exist: a locked data/scripts/<slug>_*.script.json (Gate-1
   approved), a sourced specs/<slug>.json, and a render-ready footage pool
   (run the `source-footage` skill first if unsure).

2. Run the closed loop (render → assess → auto-fix → re-render):
   `carshorts autoloop <slug>`
   It quarantines any vision-blocked clip (plate/wrong-vehicle/watermark) and
   re-renders; revises the script if the critic is below bar; and SURFACES a
   footage gap (a REPEAT/LOOP red it can't invent past) with a shopping list.

3. Read the decision trace. Outcomes:
   - shipped     → QA-green, vision-clean, critic passed. Continue to Gate 2.
   - needs_owner → act on the printed reason: footage gap → `source-footage`;
     otherwise inspect the manifest/critique and fix the root cause.

4. VERIFY BY LOOKING — never trust "done" blind. Extract frames and read them:
   `ffmpeg -i out/<slug>_draft.mp4 -vf "fps=1,scale=320:-1,tile=5x3" -frames:v 1 /tmp/grid.png`
   Confirm: opens on the moving subject car, closes on the subject car, every
   named number/feature has a synced on-screen pop, no plate/rival badge, no
   repeated clip.

5. For a one-off render outside the loop:
   `carshorts produce --script-file <script> --spec <spec> --skip-factcheck --persona <persona> --out out/<slug>_draft.mp4`
   then `carshorts qa <manifest>` and confirm the board is all green.

Gate: never surface a non-green render to the owner. QA-green + vision-clean is the
floor, not the target. Gate 1 (script) and Gate 2 (final watch) belong to the owner.
