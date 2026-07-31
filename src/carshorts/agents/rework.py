"""Auto-rework worker — a portal 'Needs rework' picks itself up.

  python -m carshorts.agents.rework <slug>     (the portal spawns this automatically)

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

from carshorts.adapters.llm import make_llm
from carshorts.core import paths
from carshorts.core.models import Script, SpecSheet
from carshorts.writing.draft import _rows, unsourced_numbers_check


def _latest_feedback(slug: str) -> dict | None:
    files = sorted(paths.FEEDBACK.glob(f"{slug}-*.json"))
    return json.loads(files[-1].read_text()) if files else None


def _render_directives(feedback: dict) -> list[str]:
    """Translate owner tags/notes into produce flags. Tags must change THIS
    render — folding them into learnings only teaches future scripts, which
    reads as the system ignoring direct orders."""
    tags = [t for ts in feedback.get("beat_tags", {}).values() for t in ts]
    notes = (feedback.get("notes") or "").lower()
    flags: list[str] = []
    if (tags.count("text on screen") >= 2
            or "remove text" in notes or "no text on screen" in notes):
        flags.append("--no-kwcaps")
    if tags.count("music") >= 2 or "remove music" in notes or "no music" in notes:
        flags.append("--music=none")
    return flags


def _fold_learnings(feedback: dict, llm) -> list[str]:
    rows = _rows(llm.complete_json(
        "Convert this owner feedback on a car Short into 1-3 concrete, "
        "actionable lessons for the script writer / renderer. beat_tags are "
        "problems to fix; beat_wins are things the owner LOVED — turn each win "
        'into a "keep doing X" lesson. Prefix nothing; '
        'output ONLY JSON: [{"lesson": "..."}]',
        json.dumps(feedback, ensure_ascii=False)))
    ldata = json.loads(paths.LEARNINGS.read_text())
    added = []
    for row in rows:
        lesson = f"[high][owner-feedback] {row.get('lesson','').strip()}"
        if row.get("lesson") and lesson not in ldata["data_learnings"]:
            ldata["data_learnings"].append(lesson)
            added.append(lesson)
    ldata["data_learnings"] = ldata["data_learnings"][-12:]
    paths.LEARNINGS.write_text(json.dumps(ldata, indent=2, ensure_ascii=False))
    return added


def _notes_to_actions(card: dict, feedback: dict, llm) -> list[str]:
    """The rework BRAIN: translate free-text owner notes into concrete render
    actions on THIS video. Without this, imperative notes ('add more overlays
    on spec beats') fold into learnings — which only teach FUTURE scripts —
    and the re-render comes back identical: the system looks deaf.

    Supported actions (LLM proposes, code validates hard):
      {"action": "add_pops", "segment": i, "pops": ["verbatim fragment", ...]}
      {"action": "set_flag", "flag": "--no-kwcaps" | "--music=none"}
    Returns human-readable descriptions of every action actually applied.
    """
    notes = (feedback.get("notes") or "").strip()
    if not notes:
        return []
    script_path = paths.resolve(card["script"])
    script = json.loads(script_path.read_text())
    segments_view = [
        {"index": i, "role": seg["role"], "text": seg["text"],
         "current_pops": [c if isinstance(c, str) else c.get("show", "")
                          for c in seg.get("pops", [])]}
        for i, seg in enumerate(script["segments"])]
    rows = _rows(llm.complete_json(
        "You translate owner feedback on a car Short into render actions. "
        "Actions available:\n"
        '  {"action": "add_pops", "segment": <i>, "pops": ["<fragment>", ...]}\n'
        "    — each fragment MUST be copied VERBATIM (word-for-word) from that "
        "segment's text, max 26 chars, 1-3 words, the strongest spec/news/"
        "figure moments not already in current_pops.\n"
        '  {"action": "set_flag", "flag": "--no-kwcaps"}   — remove ALL text\n'
        '  {"action": "set_flag", "flag": "--music=none"}  — remove music\n'
        "Apply ONLY what the owner asked. Output ONLY a JSON array (may be "
        "empty).",
        json.dumps({"owner_notes": notes, "segments": segments_view},
                   ensure_ascii=False)))
    applied: list[str] = []
    changed_script = False
    for row in rows:
        if row.get("action") == "add_pops":
            try:
                seg = script["segments"][int(row.get("segment", -1))]
            except (ValueError, IndexError):
                continue
            for frag in row.get("pops", []):
                if (isinstance(frag, str) and 0 < len(frag) <= 26
                        and frag.lower() in seg["text"].lower()
                        and frag not in seg.get("pops", [])):
                    seg.setdefault("pops", []).append(frag)
                    changed_script = True
                    applied.append(f"pop '{frag}' -> beat {row['segment']}")
        elif row.get("action") == "set_flag":
            # LLM proposes, code disposes: a removal flag needs the owner to
            # have SAID remove — one misfire stripped a whole render of text
            flag = row.get("flag", "")
            notes_l = notes.lower()
            explicit = ((flag == "--no-kwcaps"
                         and ("remove text" in notes_l or "no text" in notes_l))
                        or (flag == "--music=none"
                            and ("remove music" in notes_l or "no music" in notes_l)))
            if explicit and flag not in card.setdefault("render_flags", []):
                card["render_flags"].append(flag)
                applied.append(f"flag {flag}")
    if changed_script:
        script_path.write_text(json.dumps(script, ensure_ascii=False, indent=2))
    return applied


def _punch_up_tagged(card: dict, feedback: dict, llm) -> bool:
    """Rewrite only the segments tagged weak-hook / joke-flat."""
    tags = feedback.get("beat_tags", {})
    targets = [int(i) for i, t in tags.items()
               if any(x in ("weak hook", "joke flat") for x in t)]
    if not targets:
        return False
    script_path = paths.resolve(card["script"])
    script = Script.model_validate_json(script_path.read_text())
    sheet = SpecSheet.model_validate_json(Path(card["spec"]).read_text())
    baseline_flags = set(unsourced_numbers_check(script, sheet))
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
            original_text = seg.text
            seg.text = rows[0]["text"].strip()
            invented = set(unsourced_numbers_check(script, sheet)) - baseline_flags
            if invented:
                seg.text = original_text  # rewrite fabricated a figure — keep owner's line
                continue
            changed = True
    if changed:
        script_path.write_text(script.model_dump_json(indent=2))
    return changed


def _progress(slug: str, step: str, done: bool = False) -> None:
    pf = paths.QUEUE / f"{slug}.progress.json"
    if done:
        pf.unlink(missing_ok=True)
        return
    pf.write_text(json.dumps({"step": step,
                              "at": datetime.datetime.now().isoformat(timespec="seconds")}))


def _feedback_is_empty(feedback: dict) -> bool:
    """Owner clicked 'rework' but left notes/tags/wins all empty.
    LLM proposes, code disposes: no explicit signal -> no changes.
    Ledger incident #1 (invented --no-kwcaps) traces to acting on non-explicit
    input. The right move here is to bounce the card back with a request for
    specifics, not to escalate to the paid deep-brain and let it guess."""
    return (not (feedback.get("notes") or "").strip()
            and not feedback.get("beat_tags")
            and not feedback.get("beat_wins"))


def run(slug: str) -> None:
    card_path = paths.QUEUE / f"{slug}.json"
    if not card_path.exists():
        sys.exit(f"no queue card for {slug}")
    card = json.loads(card_path.read_text())
    feedback = _latest_feedback(slug)
    if not feedback:
        sys.exit("no feedback found")

    if _feedback_is_empty(feedback):
        card["status"] = "awaiting_approval"
        card["note"] = (f"REWORK RECEIVED {datetime.date.today()} but empty "
                        f"(no notes, no beat tags, no wins) — nothing changed. "
                        f"Tag the weak beats or leave a note describing what "
                        f"you want fixed, then click Needs rework again.")
        card_path.write_text(json.dumps(card, indent=2))
        _progress(slug, "", done=True)
        log = paths.BRAIN_LOG
        with log.open("a") as fh:
            fh.write(json.dumps({"at": datetime.datetime.now().isoformat(timespec="seconds"),
                                 "kind": "rework_empty", "slug": slug}) + "\n")
        print(f"rework skipped for {slug}: empty feedback")
        return

    if not (feedback.get("notes", "").strip() or feedback.get("beat_tags")
            or feedback.get("beat_wins")):
        # empty rework click: nothing to act on — never burn an agent run on it
        card["status"] = "awaiting_approval"
        card["note"] = ("Rework requested with no tags or notes — tell me what "
                        "to change (tag beats or write a note) and I'll act.")
        card_path.write_text(json.dumps(card, indent=2))
        _progress(slug, "", done=True)
        print(f"rework skipped for {slug}: empty feedback")
        return

    llm = make_llm(None)
    _progress(slug, "1/4 folding your feedback into learnings")
    lessons = _fold_learnings(feedback, llm)
    for flag in _render_directives(feedback):
        if flag not in card.setdefault("render_flags", []):
            card["render_flags"].append(flag)
    _progress(slug, "2/4 translating your notes into render actions")
    actions = _notes_to_actions(card, feedback, llm)
    _progress(slug, "3/4 rewriting tagged beats")
    rewrote = _punch_up_tagged(card, feedback, llm)

    if not (actions or rewrote or _render_directives(feedback)):
        # NOTHING in the free brain's menu maps to this feedback. Escalate to
        # the deep brain: a headless Claude session with repo access that can
        # change code, re-render and verify — then grow the menu so the free
        # brain handles this class of feedback next time.
        from carshorts.agents.agent import run_agent
        _progress(slug, "escalating to the deep brain (Claude mechanic)…")
        outcome = run_agent("mechanic", (
            f"Owner feedback on queue card {slug} maps to no action in the "
            f"free rework brain. Make the owner's request real in the DRAFT "
            f"video, re-render, verify QA green, re-queue the card.\n\n"
            f"Feedback JSON: {json.dumps(feedback, ensure_ascii=False)}\n"
            f"Card: data/queue/{slug}.json\n"
            f"Script: {card['script']}\nSpec: {card['spec']}\n"
            f"Draft out path: {card['draft']}"))
        card = json.loads(card_path.read_text())   # mechanic may have edited it
        if outcome["ok"]:
            if card.get("status") != "awaiting_approval":
                card["status"] = "awaiting_approval"
            card["note"] = ("DEEP-BRAIN REWORK " + str(datetime.date.today())
                            + ": " + str(outcome["result"])[:220])
        else:
            card["status"] = "awaiting_approval"
            card["note"] = (f"REWORK SKIPPED {datetime.date.today()}: feedback "
                            f"saved as a lesson; deep brain unavailable "
                            f"({str(outcome['result'])[:120]}). Tag beats or "
                            f"give a concrete instruction.")
        card_path.write_text(json.dumps(card, indent=2))
        _progress(slug, "", done=True)
        log = paths.BRAIN_LOG
        with log.open("a") as fh:
            fh.write(json.dumps({"at": datetime.datetime.now().isoformat(timespec="seconds"),
                                 "kind": "escalation", "slug": slug,
                                 "ok": outcome["ok"]}) + "\n")
        print(f"rework escalated for {slug}: ok={outcome['ok']}")
        return

    step3 = "4/4 re-rendering the draft (~2 min)"
    if "--no-kwcaps" in card.get("render_flags", []):
        step3 = "3/3 re-rendering WITHOUT text overlays (~2 min)"
    _progress(slug, step3)
    result = subprocess.run(
        [sys.executable, "-m", "carshorts.rendering.produce", "--script-file", card["script"],
         "--spec", card["spec"], "--skip-factcheck", "--persona",
         card.get("persona", "deadpan"), "--out", card["draft"],
         *card.get("render_flags", [])],
        capture_output=True, text=True)
    ok = result.returncode == 0
    qa_green = "QA FAILED" not in (result.stdout or "")

    card["status"] = "awaiting_approval" if ok else "rework_failed"
    flags_note = ""
    if "--no-kwcaps" in card.get("render_flags", []):
        flags_note += ", TEXT OVERLAYS REMOVED"
    if "--music=none" in card.get("render_flags", []):
        flags_note += ", MUSIC REMOVED"
    action_note = f", {len(actions)} note-action(s): " + "; ".join(actions[:3]) if actions else ""
    card["note"] = (f"AUTO-REWORK {datetime.date.today()}: "
                    f"{len(lessons)} lesson(s) folded"
                    + (", tagged jokes rewritten" if rewrote else "")
                    + action_note
                    + flags_note
                    + ", re-rendered"
                    + ("" if qa_green else " — ⚠ QA flagged, check before approving"))
    card_path.write_text(json.dumps(card, indent=2))
    _progress(slug, "", done=True)

    log = paths.BRAIN_LOG
    with log.open("a") as fh:
        fh.write(json.dumps({"at": datetime.datetime.now().isoformat(timespec="seconds"),
                             "kind": "rework", "slug": slug, "ok": ok,
                             "lessons": len(lessons), "rewrote": rewrote}) + "\n")
    print(f"rework {'done' if ok else 'FAILED'} for {slug}")


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "")
