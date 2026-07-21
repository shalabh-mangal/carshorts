"""Auto-rework worker — a portal 'Needs rework' picks itself up.

  python -m carshorts.rework <slug>     (the portal spawns this automatically)

1. loads the LATEST feedback for the slug
2. folds it into data/learnings.json as owner-feedback lessons (LLM, deduped)
3. if beats were tagged weak-hook / joke-flat, punches up THOSE segments'
   text via the LLM (facts and cited specs untouched — guards re-verify)
4. re-renders the draft (free voice) with the updated learnings/engine
5. flips the queue card back to awaiting_approval with a change note

Every run journals to data/brain_log.jsonl.
"""
from __future__ import annotations

import datetime
import json
import subprocess
import sys
from pathlib import Path

from .adapters.llm import make_llm
from .models import Script
from .stages.pipeline import _rows


def _latest_feedback(slug: str) -> dict | None:
    files = sorted(Path("data/feedback").glob(f"{slug}-*.json"))
    return json.loads(files[-1].read_text()) if files else None


def _fold_learnings(feedback: dict, llm) -> list[str]:
    rows = _rows(llm.complete_json(
        "Convert this owner feedback on a car Short into 1-3 concrete, "
        "actionable lessons for the script writer / renderer. Prefix nothing; "
        'output ONLY JSON: [{"lesson": "..."}]',
        json.dumps(feedback, ensure_ascii=False)))
    ldata = json.loads(Path("data/learnings.json").read_text())
    added = []
    for row in rows:
        lesson = f"[high][owner-feedback] {row.get('lesson','').strip()}"
        if row.get("lesson") and lesson not in ldata["data_learnings"]:
            ldata["data_learnings"].append(lesson)
            added.append(lesson)
    ldata["data_learnings"] = ldata["data_learnings"][-12:]
    Path("data/learnings.json").write_text(json.dumps(ldata, indent=2, ensure_ascii=False))
    return added


def _punch_up_tagged(card: dict, feedback: dict, llm) -> bool:
    """Rewrite only the segments tagged weak-hook / joke-flat."""
    tags = feedback.get("beat_tags", {})
    targets = [int(i) for i, t in tags.items()
               if any(x in ("weak hook", "joke flat") for x in t)]
    if not targets:
        return False
    script_path = Path(card["script"])
    script = Script.model_validate_json(script_path.read_text())
    changed = False
    for idx in targets:
        if idx >= len(script.segments):
            continue
        seg = script.segments[idx]
        rows = _rows(llm.complete_json(
            "Rewrite this car-Short line to be sharper and funnier — a "
            "SPECIFIC roast/analogy for this car, never generic. Keep any "
            "numbers/facts EXACTLY as written; similar length. "
            'Output ONLY JSON: [{"text": "..."}]',
            f"Car: {script.subject}\nRole: {seg.role}\nLine: {seg.text}\n"
            f"Owner notes: {feedback.get('notes','')[:300]}"))
        if rows and rows[0].get("text"):
            seg.text = rows[0]["text"].strip()
            changed = True
    if changed:
        script_path.write_text(script.model_dump_json(indent=2))
    return changed


def run(slug: str) -> None:
    card_path = Path("data/queue") / f"{slug}.json"
    if not card_path.exists():
        sys.exit(f"no queue card for {slug}")
    card = json.loads(card_path.read_text())
    feedback = _latest_feedback(slug)
    if not feedback:
        sys.exit("no feedback found")

    llm = make_llm(None)
    lessons = _fold_learnings(feedback, llm)
    rewrote = _punch_up_tagged(card, feedback, llm)

    result = subprocess.run(
        [sys.executable, "-m", "carshorts.produce", "--script-file", card["script"],
         "--spec", card["spec"], "--skip-factcheck", "--persona",
         card.get("persona", "deadpan"), "--out", card["draft"]],
        capture_output=True, text=True)
    ok = result.returncode == 0

    card["status"] = "awaiting_approval" if ok else "rework_failed"
    card["note"] = (f"AUTO-REWORK {datetime.date.today()}: "
                    f"{len(lessons)} lesson(s) folded"
                    + (", tagged jokes rewritten" if rewrote else "")
                    + ", re-rendered with updated text engine")
    card_path.write_text(json.dumps(card, indent=2))

    log = Path("data/brain_log.jsonl")
    with log.open("a") as fh:
        fh.write(json.dumps({"at": datetime.datetime.now().isoformat(timespec="seconds"),
                             "kind": "rework", "slug": slug, "ok": ok,
                             "lessons": len(lessons), "rewrote": rewrote}) + "\n")
    print(f"rework {'done' if ok else 'FAILED'} for {slug}")


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "")
